"""Günlük ihtiyaçtan bağımsız, tüm ay için uygulanabilir kota dağılımı."""
import calendar
import hashlib
import json
import time
from datetime import date
from ortools.sat.python import cp_model
from nobet_tani import build_rules
from nobet_rotasyon import add_rotation_preferences, rotation_warnings, add_incoming_preferences, incoming_warnings


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate(data):
    docs = data['docs']
    if not docs:
        raise ValueError('Önce personel ekleyin.')
    if len(set(docs)) != len(docs) or any(not d.strip() for d in docs):
        raise ValueError('Personel isimleri boş veya tekrarlı olamaz.')
    n = calendar.monthrange(data['year'], data['month'])[1]
    for doc in docs:
        for key in ('q24', 'q16'):
            v = data[key].get(doc, 0)
            if isinstance(v, bool) or int(v) != v or not 0 <= v <= 31:
                raise ValueError(f'{doc}: nöbet sayısı 0–31 arasında tam sayı olmalı.')
    if not 1 <= data['rest'] <= 5:
        raise ValueError('Dinlenme ayarı 1–5 gün olmalı.')
    return n


def _secondary_terms(m, data, docs, n, manual, x24, x16, best_total):
    """Toplam sabitken ikincil tercihleri kurar: (soft, secondary, bound).

    soft: S izni ihlalleri; secondary: günlük dağılım/kıdem/eş/rotasyon cezaları.
    Bir S ihlali, diğer ikincil maliyetlerin tamamından daha ağırdır (bound).
    """
    secondary, soft = [], []
    for t in range(1,n+1):
        daily = sum(x24[d,t]+x16[d,t] for d in docs)
        dev = m.NewIntVar(0,n*len(docs),f'daily_dev_{t}')
        m.AddAbsEquality(dev, n*daily-best_total)
        secondary.append(dev*10)
        for d in docs:
            if manual.get(f'{d}_{t}') == 'S':
                soft.append(x24[d,t]+x16[d,t])
    seniors=[d for d in docs if data.get('seniority',{}).get(d)=='Kıdemli']
    mids=[d for d in docs if data.get('seniority',{}).get(d)=='Orta']
    for t in range(1,n+1):
        if seniors and mids:
            diff=m.NewIntVar(0,len(docs),f'seniority_{t}')
            m.AddAbsEquality(diff,sum(x24[d,t] for d in seniors)-sum(x24[d,t] for d in mids))
            secondary.append(diff)
    valid_pairs=[p for p in data.get('couples',[]) if len(p)==2 and p[0] in docs and p[1] in docs]
    for i,(a,b) in enumerate(valid_pairs):
        for t in range(1,n+1):
            diff=m.NewBoolVar(f'pair_{i}_{t}')
            m.AddAbsEquality(diff,x24[a,t]+x16[a,t]-x24[b,t]-x16[b,t])
            secondary.append(diff*2)
    # Yeni tercihlerin toplamı da S izninin önceliğini düşürmemeli.
    bound = 10*n*n*len(docs)+n*len(docs)+2*n*len(valid_pairs)+1
    rotation = [d for d in docs if d in data.get('rotation_doctors', [])]
    incoming=[d for d in docs if d in data.get('incoming',[])]
    secondary.extend(add_rotation_preferences(
        m, docs, rotation, data['year'], data['month'], x24, x16,
    ))
    secondary.extend(add_incoming_preferences(
        m, docs, incoming, data['year'], data['month'], x24, x16,
    ))
    bound += 100*n*(max(0,len(rotation)-1)+len(rotation))
    bound += 100*n*max(0,len(incoming)-1)
    return soft, secondary, bound


def _phase2_model(data, docs, n, manual, best_total, window):
    """Büyük ekipler için faz 2: sert kurallı taze model; pencere günlük sayıları kilitler.

    Tanılama assumption'ları amacsız çözücüde aramayı felç ettiği için bu model
    kuralları doğrudan sert kısıt olarak kurar (diagnostic=False). İkincil terim
    değişkenleri (denge/kıdem/eş) aramayı yavaşlattığından burada YOKTUR;
    cilama aşamasında ayrıca eklenir. Yalnızca S ihlali ifadeleri döner.
    """
    m2 = cp_model.CpModel()
    a24, a16, _, _, _ = build_rules(m2, docs, n, data['rest'], {}, {}, manual,
                                    diagnostic=False, free_capacity=True)
    counts = []
    for doc in docs:
        for hours, variables, qkey in ((24,a24,'q24'),(16,a16,'q16')):
            count = sum(variables[doc,t] for t in range(1,n+1))
            counts.append(count)
            m2.Add(count <= int(data[qkey].get(doc,0)))
    m2.Add(sum(counts) == best_total)
    soft=[]
    for t in range(1,n+1):
        daily = sum(a24[d,t]+a16[d,t] for d in docs)
        if window:
            lo, hi = window
            m2.Add(lo <= daily)
            m2.Add(daily <= hi)
        for d in docs:
            if manual.get(f'{d}_{t}') == 'S':
                soft.append(a24[d,t]+a16[d,t])
    return m2, a24, a16, soft


def compute(data, seconds=20):
    n = validate(data)
    docs, manual = data['docs'], data['manual']
    model = cp_model.CpModel()
    x24, x16, _, labels, _ = build_rules(model, docs, n, data['rest'], {}, {}, manual,
                                        diagnostic=True, free_capacity=True)
    # Kotalar ön incelemede üst sınırdır; sabit nöbetlerle çelişirse açıklanır.
    counts = {}
    for doc in docs:
        for hours, variables, qkey in ((24,x24,'q24'), (16,x16,'q16')):
            count = sum(variables[doc,t] for t in range(1,n+1))
            counts[doc,hours] = count
            quota = int(data[qkey].get(doc,0))
            guard = model.NewBoolVar(f'quota_{len(labels)}')
            model.Add(count <= quota).OnlyEnforceIf(guard)
            model.AddAssumption(guard)
            labels[guard.Index()] = {'text':f'{doc}: {hours} saat nöbet üst sınırı {quota}.'}
    total = sum(counts.values())
    target = sum(int(data[q].get(d,0)) for d in docs for q in ('q24','q16'))
    deadline = time.monotonic() + max(1, seconds)
    solver = cp_model.CpSolver()
    # Faz 1 hızlıdır ve tek işçi belirleyici kalır; paralellik yalnızca faz 2'nin
    # büyük ekip dalında açılır.
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = max(.1, seconds*.65)
    model.Maximize(total)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reasons = []
        if status == cp_model.INFEASIBLE:
            # Amaçsız tanılama: yalnızca temel kurallar ve kota üst sınırları.
            model.ClearObjective()
            solver.parameters.max_time_in_seconds = max(.1, deadline-time.monotonic())
            diag_status = solver.Solve(model)
            if diag_status == cp_model.INFEASIBLE:
                reasons = [labels[i]['text'] for i in solver.SufficientAssumptionsForInfeasibility()]
        return {'status':solver.StatusName(status), 'reasons': reasons}
    best_total = solver.Value(total)
    proven = status == cp_model.OPTIMAL or best_total == target

    def capture():
        return {(doc,t): 24 if solver.Value(x24[doc,t]) else 16 if solver.Value(x16[doc,t]) else 0
                for doc in docs for t in range(1,n+1)}
    def from_model(a24,a16):
        return {(doc,t): 24 if solver.Value(a24[doc,t]) else 16 if solver.Value(a16[doc,t]) else 0
                for doc in docs for t in range(1,n+1)}
    assignment = capture()
    # Toplamdan ödün vermeden esnek izin, günlük dağılım, eş/kıdem tercihleri.
    model.Add(total == best_total)
    second_status=None
    if len(docs)*n < 400:
        # Küçük ekipler: tek işçili belirleyici denge aşaması yeterince hızlıdır.
        soft, secondary, bound = _secondary_terms(model, data, docs, n, manual, x24, x16, best_total)
        model.Minimize(sum(soft)*bound+sum(secondary))
        remaining=deadline-time.monotonic()
        if remaining > .05:
            for doc in docs:
                for t in range(1,n+1):
                    model.AddHint(x24[doc,t],int(assignment[doc,t]==24))
                    model.AddHint(x16[doc,t],int(assignment[doc,t]==16))
            solver.parameters.max_time_in_seconds=remaining
            second_status=solver.Solve(model)
            if second_status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
                assignment=capture()
    else:
        # Büyük ekiplerde ceza araması dengeye sürede inemiyor. Günlük sayılar
        # ortalamaya sabitlenir; pencere içinde önce S ihlalleri en aza indirilir,
        # bulunan S sayısı sabitlenip kalan süre diğer tercihlerin cilasına ayrılır.
        solver.parameters.num_search_workers = 8
        lo0, hi0 = best_total // n, -(-best_total // n)
        solved=None
        for k in range(4):
            remaining=deadline-time.monotonic()
            budget=remaining-0.2 if k==3 else min(max(6.0, remaining*0.5), remaining-0.2)
            if budget <= 0.1:
                break
            m2,a24,a16,soft=_phase2_model(data, docs, n, manual, best_total, (max(0,lo0-k), hi0+k))
            m2.Minimize(sum(soft) if soft else sum(a24[d,1]+a16[d,1] for d in docs))
            solver.parameters.max_time_in_seconds=budget
            second_status=solver.Solve(m2)
            if second_status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
                solved=(m2,a24,a16,soft)
                assignment=from_model(a24,a16)
                break
        if solved is None:
            # Pencereler sürede çözülemedi: penceresiz, S öncelikli iki aşama.
            remaining=deadline-time.monotonic()
            if remaining > 0.3:
                m2,a24,a16,soft=_phase2_model(data, docs, n, manual, best_total, None)
                m2.Minimize(sum(soft) if soft else sum(a24[d,1]+a16[d,1] for d in docs))
                solver.parameters.max_time_in_seconds=max(.1, remaining*0.5)
                second_status=solver.Solve(m2)
                if second_status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
                    assignment=from_model(a24,a16)
                    remaining=deadline-time.monotonic()
                    if remaining > 0.1:
                        if soft:
                            m2.Add(sum(soft) == solver.Value(sum(soft)))
                        _,secondary,_=_secondary_terms(m2, data, docs, n, manual, a24, a16, best_total)
                        m2.Minimize(sum(secondary))
                        solver.parameters.max_time_in_seconds=remaining
                        st=solver.Solve(m2)
                        if st in (cp_model.OPTIMAL,cp_model.FEASIBLE):
                            second_status=st
                            assignment=from_model(a24,a16)
        else:
            # Cila: S sayısını sabitle, kalan sürede dağılım/kıdem/eş/rotasyonu iyileştir.
            m2,a24,a16,soft=solved
            remaining=deadline-time.monotonic()
            if remaining > 0.5:
                if soft:
                    m2.Add(sum(soft) == solver.Value(sum(soft)))
                _,secondary,_=_secondary_terms(m2, data, docs, n, manual, a24, a16, best_total)
                for doc in docs:
                    for t in range(1,n+1):
                        m2.AddHint(a24[doc,t],int(assignment[doc,t]==24))
                        m2.AddHint(a16[doc,t],int(assignment[doc,t]==16))
                m2.Minimize(sum(secondary))
                solver.parameters.max_time_in_seconds=remaining
                st=solver.Solve(m2)
                if st in (cp_model.OPTIMAL,cp_model.FEASIBLE):
                    second_status=st
                    assignment=from_model(a24,a16)
    rows=[]
    for t in range(1,n+1):
        a=[d for d in docs if assignment[d,t]==24]
        b=[d for d in docs if assignment[d,t]==16]
        rows.append({'day':t,'date':date(data['year'],data['month'],t).isoformat(),
                     'n24':len(a),'n16':len(b),'team24':a,'team16':b})
    stats=[]
    for d in docs:
        a=sum(assignment[d,t]==24 for t in range(1,n+1))
        b=sum(assignment[d,t]==16 for t in range(1,n+1))
        stats.append({'Doktor':d,'24s hedef':int(data['q24'].get(d,0)), '24s yazılan':a,
                      '24s eksik':int(data['q24'].get(d,0))-a,
                      '16s hedef':int(data['q16'].get(d,0)), '16s yazılan':b,
                      '16s eksik':int(data['q16'].get(d,0))-b})
    violations=[f'{d}: {t}. gün {assignment[d,t]} saat' for d in docs for t in range(1,n+1)
                if manual.get(f'{d}_{t}')=='S' and assignment[d,t]]
    rotation = [d for d in docs if d in data.get('rotation_doctors', [])]
    incoming=[d for d in docs if d in data.get('incoming',[])]
    rotation_notes = rotation_warnings(
        rotation, data['year'], data['month'],
        {d: [t for t in range(1,n+1) if assignment[d,t]] for d in rotation},
    )
    incoming_notes = incoming_warnings(
        incoming, data['year'], data['month'],
        {d: [t for t in range(1,n+1) if assignment[d,t]] for d in incoming},
    )
    daily=[r['n24']+r['n16'] for r in rows]
    spread=max(daily)-min(daily)
    # Denge aşaması OPTIMAL'a ulaştıysa veya günler arası fark en fazla 1 ise dengeli sayılır.
    balanced=second_status==cp_model.OPTIMAL or spread<=1
    return {'status':'OK','rows':rows,'stats':stats,'target':target,'assigned':best_total,
            'proven':proven,'violations':violations,'rotation_warnings':rotation_notes,
            'incoming_warnings':incoming_notes,'daily':daily,'spread':spread,'balanced':balanced}


def validate_reduction(rows, result, manual):
    if len(rows)!=len(result['rows']):
        raise ValueError('Gün sayısı değiştirilemez.')
    needs24,needs16={},{}
    for entry,original in zip(rows,result['rows']):
        day=original['day']
        for col,hours,key,out in [('24 saat',24,'n24',needs24),('16 saat',16,'n16',needs16)]:
            value=entry[col]
            if value is None or isinstance(value,bool) or int(value)!=value or not 0<=value<=original[key]:
                raise ValueError(f'{day}. gün: {hours} saat sayısı 0–{original[key]} arasında tam sayı olmalı; yalnızca azaltılabilir.')
            fixed=sum(manual.get(f'{d}_{day}')==str(hours) for d in original[f'team{hours}'])
            if value<fixed:
                raise ValueError(f'{day}. gün: {fixed} sabit {hours} saat nöbet var; bunun altına azaltılamaz.')
            out[day]=int(value)
    return needs24,needs16


def istek_karsilastirma_satirlari(docs, manual, duties, year, month):
    """İstek (X/S/24/16) ile yazılan nöbetlerin fark matriksi satırları.

    duties: {kişi: {gün: '24' veya '16'}}. Hücre kuralları:
      '24'/'16'      nöbet yazıldı; istek yok ya da sabit istek yerine geldi
      'S→24'/'S→16'  esnek izin istenen güne nöbet yazıldı
      'X'/'S'        izin istendi, nöbet yazılmadı (isteğe uyuldu)
      '24!'/'16!'    sabit istenen nöbet yazılmadı (hata durumu)
      'X→24' vb.     kesin izin gününe nöbet / sabitten farklı tip (hata durumu)
    """
    n = calendar.monthrange(year, month)[1]
    rows = []
    for d in docs:
        row = {'Personel': d}
        for t in range(1, n+1):
            istek = manual.get(f'{d}_{t}', '')
            yazilan = duties.get(d, {}).get(t, '')
            if yazilan and istek == 'S':
                hucre = f'S→{yazilan}'
            elif yazilan and istek == 'X':
                hucre = f'X→{yazilan}'
            elif yazilan and istek in ('24', '16') and istek != yazilan:
                hucre = f'{istek}→{yazilan}'
            elif yazilan:
                hucre = yazilan
            elif istek in ('24', '16'):
                hucre = f'{istek}!'
            else:
                hucre = istek
            row[f'{t:02d}.{month:02d}'] = hucre
        rows.append(row)
    return rows


def export_report(data, result, month_names):
    """Ön inceleme sonuçlarını Excel raporu baytlarına dönüştürür."""
    import io
    import pandas as pd
    summary = [('Rapor', 'Ön inceleme — aylık nöbet dağılımı'),
               ('Ay', f"{month_names[data['month']]} {data['year']}"),
               ('Hedef toplam', result['target']),
               ('Yazılan toplam', result['assigned']),
               ('Eksik', result['target'] - result['assigned']),
               ('En yüksek olduğu kanıtlandı', 'Evet' if result['proven'] else 'Hayır'),
               ('Günlük kural', 'Her gün en fazla 2 kişi 16 saat nöbet tutabilir.')]
    daily = [{'Gün': r['day'], 'Tarih': r['date'], '24 saat': r['n24'], '16 saat': r['n16'],
              'Toplam': r['n24'] + r['n16']} for r in result['rows']]
    schedule = [{'Gün': r['day'], 'Tarih': r['date'], '24 saat': ', '.join(r['team24']),
                 '16 saat': ', '.join(r['team16'])} for r in result['rows']]
    warnings = ([f'S izni: {v}' for v in result['violations']]
                + list(result.get('rotation_warnings', []))
                + list(result.get('incoming_warnings', [])))
    if not result.get('balanced', True) and result.get('daily'):
        warnings.append(f"Günlük dağılım bu sürede tam dengelenmedi (günler {min(result['daily'])}–"
                        f"{max(result['daily'])} kişi); düşünme süresi artırılırsa iyileşebilir.")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        pd.DataFrame(summary, columns=['Alan', 'Değer']).to_excel(writer, sheet_name='Ozet', index=False)
        pd.DataFrame(daily).to_excel(writer, sheet_name='Gunluk Dagilim', index=False)
        pd.DataFrame(result['stats']).to_excel(writer, sheet_name='Kisi Bazinda', index=False)
        # Kişisel nöbet matriksi: satırlar kişiler, sütunlar ayın günleri, hücrede 24/16.
        duties = {d: {} for d in data['docs']}
        for r in result['rows']:
            for d in r['team24']:
                duties[d][r['day']] = '24'
            for d in r['team16']:
                duties[d][r['day']] = '16'
        matrix = []
        for d in data['docs']:
            row = {'Personel': d}
            toplam = 0
            for r in result['rows']:
                v = duties[d].get(r['day'], '')
                row[f"{r['day']:02d}.{data['month']:02d}"] = v
                toplam += bool(v)
            row['Toplam'] = toplam
            matrix.append(row)
        pd.DataFrame(matrix).to_excel(writer, sheet_name='Kisi Nobetleri', index=False)
        kars = istek_karsilastirma_satirlari(data['docs'], data['manual'], duties, data['year'], data['month'])
        pd.DataFrame(kars).to_excel(writer, sheet_name='Istek Karsilastirma', index=False)
        pd.DataFrame(schedule).to_excel(writer, sheet_name='Ornek Cizelge', index=False)
        if warnings:
            pd.DataFrame({'Uyarılar': warnings}).to_excel(writer, sheet_name='Uyarilar', index=False)
        writer.sheets['Ornek Cizelge'].set_column(2, 3, 40)
        ws_k = writer.sheets['Kisi Nobetleri']
        ws_k.set_column(0, 0, 15)
        ws_k.set_column(1, len(result['rows']), 5)
        wb = writer.book
        fmt_k24 = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'bold': True})
        fmt_k16 = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'bold': True})
        ws_k.conditional_format(1, 1, len(matrix), len(result['rows']),
                                {'type': 'cell', 'criteria': '==', 'value': '"24"', 'format': fmt_k24})
        ws_k.conditional_format(1, 1, len(matrix), len(result['rows']),
                                {'type': 'cell', 'criteria': '==', 'value': '"16"', 'format': fmt_k16})
        ws_c = writer.sheets['Istek Karsilastirma']
        ws_c.set_column(0, 0, 15)
        ws_c.set_column(1, len(result['rows']), 6)
        fmt_y = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        fmt_o = wb.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500', 'bold': True})
        fmt_g = wb.add_format({'bg_color': '#E7E6E6', 'font_color': '#595959'})
        fmt_r = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'bold': True})
        aralik = (1, 1, len(kars), len(result['rows']))
        for deger, f in [('"24"', fmt_y), ('"16"', fmt_y), ('"X"', fmt_g), ('"S"', fmt_g)]:
            ws_c.conditional_format(*aralik, {'type': 'cell', 'criteria': '==', 'value': deger,
                                              'format': f, 'stop_if_true': True})
        for metin, f in [('S→', fmt_o), ('!', fmt_r), ('→', fmt_r)]:
            ws_c.conditional_format(*aralik, {'type': 'text', 'criteria': 'containing', 'value': metin,
                                              'format': f, 'stop_if_true': True})
    return buf.getvalue()


def render(st, rest_days, calc_time, month_names):
    import pandas as pd
    ss=st.session_state
    st.subheader('🔎 Ön İnceleme — Aylık Nöbet Dağılımı')
    st.info('Kota & Kıdem ile İzin & İstekler sekmelerindeki girişlerinizi kaydedin. Günlük ihtiyaç girmeniz gerekmez. Her gün en fazla 2 kişi 16 saat çalışır.')
    st.caption('Önce yazılabilen toplam nöbet sayısı en yüksek tutulur; ardından esnek izinler ve günlük denge gözetilir. Kotalar aşılmaz. Bu tablo tüm ay için tek bir uygulanabilir dağılımdır; günlerin bağımsız maksimumları değildir.')
    st.caption('Rotasyon seçimleri de değerlendirilir: mümkün olduğunca farklı günler ve kişi başına ayda en fazla 2 cumartesi/pazar nöbeti hedeflenir. Bu esnek tercihler toplam nöbet sayısını azaltmaz.')
    st.caption('Rotasyona gelenler kenar çubuğundan seçilir: her gün gruptan mümkün olduğunca tek kişi yazılır; zorunlu kurallar gereği aynı güne düşenler uyarı olarak listelenir.')
    st.caption('Çok karmaşık ve kısıtları çok olan seçimlerde; daha iyi bir sonuç için düşünme süresini mümkün olduğunca yüksek tutmaya çalışın.')
    data={'docs':list(ss.doctors),'year':int(ss.year),'month':int(ss.month),'rest':int(rest_days),
          'q24':dict(ss.quotas_24h),'q16':dict(ss.quotas_16h),'manual':dict(ss.manual_constraints),
          'seniority':dict(ss.seniority),'couples':list(ss.couples),
          'rotation_doctors':list(ss.get('rotation_doctors',[])),
          'incoming':list(ss.get('incoming_rotation',[]))}
    sig=fingerprint(data)
    if st.button('🔎 Ön İnceleme Yap',type='primary',key='preview_run'):
        try:
            with st.spinner('Tüm ayın uygulanabilir dağılımı hesaplanıyor...'):
                result=compute(data,calc_time)
            ss['preview_result']={'signature':sig,'result':result}
            ss['preview_revision']=ss.get('preview_revision',0)+1
        except (ValueError,TypeError,OverflowError) as exc:
            ss.pop('preview_result',None)
            st.error(f'Girişleri kontrol edin: {exc}')
    saved=ss.get('preview_result')
    if not saved:
        return
    if saved['signature']!=sig:
        st.warning('Ay, personel, kota, rotasyon veya kurallar değişti. Güncel tablo için ön incelemeyi yeniden çalıştırın.')
        return
    result=saved['result']
    if result['status']!='OK':
        if result['status']=='INFEASIBLE':
            st.error('Sabit nöbetler, izinler, dinlenme veya kota üst sınırları çelişiyor. Uygulanabilir tablo oluşturulamadı.')
            for reason in result['reasons']:
                st.write('• '+reason)
            st.caption('Gösterilen kural grubu en küçük grup olmayabilir. Sabit nöbet sayısı kotadan fazlaysa ilgili kotayı veya sabit kaydı düzeltin.')
        elif result['status']=='UNKNOWN':
            st.warning('Süre içinde tablo bulunamadı; imkânsız olduğu kanıtlanmadı. Düşünme süresini artırıp tekrar deneyin.')
        else:
            st.error('Ön inceleme modeli doğrulanamadı. Girdi değerlerini kontrol edin.')
        return
    if result['assigned']==result['target']:
        st.success(f"Tüm kotalar karşılandı: {result['assigned']} nöbet.")
    elif result['proven']:
        st.warning(f"Hedef {result['target']}, yazılabilen en fazla {result['assigned']}, eksik {result['target']-result['assigned']}. Eksikler aşağıdaki kişi tablosunda.")
    else:
        st.warning(f"Hedef {result['target']}, bu sürede yazılabilen {result['assigned']}. Bunun en yüksek sayı olduğu kanıtlanmadı; süre artırılırsa daha fazlası bulunabilir.")
    if result.get('daily'):
        lo,hi=min(result['daily']),max(result['daily'])
        if result.get('balanced'):
            st.caption(f"Günlük dağılım dengeli: her gün {lo}–{hi} nöbetçi.")
        else:
            st.warning(f"Günlük dağılım bu sürede tam dengelenemedi: günler {lo}–{hi} nöbetçi arasında. Düşünme süresini artırıp tekrar deneyin.")
    st.download_button('📥 Ön İnceleme Raporunu İndir (Excel)', export_report(data, result, month_names),
                       f"On_Inceleme_{data['year']}_{data['month']:02d}.xlsx",
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    rows=[{'Tarih':f"{r['day']} {month_names[ss.month]}", '24 saat':r['n24'],'16 saat':r['n16']}
          for r in result['rows']]
    st.caption('Günlük sayıları isterseniz azaltın; ardından günlük ihtiyaçlara aktarın. Azaltınca bazı kotalar eksik kalacaktır.')
    with st.form('preview_transfer_form'):
        edited=st.data_editor(pd.DataFrame(rows),hide_index=True,use_container_width=True,
                  height=650,key=f"preview_table_{ss.get('preview_revision',0)}",
                  column_config={'Tarih':st.column_config.TextColumn(disabled=True),
                    '24 saat':st.column_config.NumberColumn(min_value=0,max_value=len(data['docs']),step=1,required=True),
                    '16 saat':st.column_config.NumberColumn(min_value=0,max_value=2,step=1,required=True)})
        transfer=st.form_submit_button('Günlük ihtiyaçlara aktar')
    if transfer:
        try:
            a,b=validate_reduction(edited.to_dict('records'),result,data['manual'])
            ss.daily_needs_24h=a
            ss.daily_needs_16h=b
            ss.editor_key+=1
            ss['preview_transfer_notice']='Ön inceleme sayıları günlük ihtiyaçlara aktarıldı. Oluştur & Sonuç sekmesinden çizelgeyi oluşturabilirsiniz.'
            st.rerun()
        except (ValueError,TypeError,OverflowError) as exc:
            st.error(str(exc))
    if ss.get('preview_transfer_notice'):
        st.success(ss.pop('preview_transfer_notice'))
    st.write('**Kişi başına nöbet sayıları — hesaplanan ilk dağılım**')
    st.dataframe(pd.DataFrame(result['stats']),hide_index=True,use_container_width=True)
    with st.expander('Dağılımı sağlayan örnek personel çizelgesi'):
        st.dataframe(pd.DataFrame([{'Tarih':rows[i]['Tarih'],'24 saat':', '.join(r['team24']),
                                   '16 saat':', '.join(r['team16'])} for i,r in enumerate(result['rows'])]),hide_index=True,use_container_width=True)
    with st.expander('İstek – yazılan nöbet karşılaştırması'):
        st.caption('Yeşil 24/16: nöbet yazıldı (istek yok ya da sabit istek yerine getirildi) · Turuncu S→24/16: esnek izin istenen güne nöbet yazıldı · Gri X/S: izin istendi, nöbet yazılmadı · Kırmızı ! veya →: hata durumu, olmaması gerekir.')
        duties_r={}
        for rr in result['rows']:
            for dd in rr['team24']: duties_r.setdefault(dd,{})[rr['day']]='24'
            for dd in rr['team16']: duties_r.setdefault(dd,{})[rr['day']]='16'
        dfk=pd.DataFrame(istek_karsilastirma_satirlari(
            data['docs'], data['manual'], duties_r, data['year'], data['month']))
        def kars_renk(v):
            if v in ('24','16'): return 'background-color: #c6efce; color: #006100'
            if isinstance(v,str) and v.startswith('S→'): return 'background-color: #ffeb9c; color: #9c6500; font-weight: bold'
            if v in ('X','S'): return 'background-color: #e7e6e6; color: #595959'
            if isinstance(v,str) and ('!' in v or '→' in v): return 'background-color: #ffc7ce; color: #9c0006; font-weight: bold'
            return ''
        st.dataframe(dfk.style.map(kars_renk),use_container_width=True,height=420)
    if result['violations']:
        with st.expander('Esnek izin (S) günlerine yazılan nöbetler',expanded=True):
            for line in result['violations']:
                st.write(line)
    if result.get('rotation_warnings'):
        with st.expander('Rotasyon tercihleri — ön incelemede karşılanamayanlar',expanded=True):
            st.caption('Bu uyarılar ön incelemedeki örnek dağılıma aittir. Ana çizelgede kişiler ve uyarılar farklı olabilir.')
            for line in result['rotation_warnings']:
                st.warning(line)
    if result.get('incoming_warnings'):
        with st.expander('Rotasyona gelenler — aynı güne yazılanlar',expanded=True):
            st.caption('Bu uyarılar ön incelemedeki örnek dağılıma aittir. Ana çizelgede kişiler ve uyarılar farklı olabilir.')
            for line in result['incoming_warnings']:
                st.warning(line)
    st.caption('Günlük ihtiyaçlara aktarım yalnızca sayıları aktarır. Ana çizelge motoru farklı kişiler seçebilir; ana motordaki kotalar mevcut sürümde esnek hedeftir.')
