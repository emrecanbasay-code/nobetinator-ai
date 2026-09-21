"""Günlük ihtiyaçtan bağımsız, tüm ay için uygulanabilir kota dağılımı."""
import calendar
import hashlib
import json
import time
from datetime import date
from ortools.sat.python import cp_model
from nobet_tani import build_rules
from nobet_rotasyon import add_rotation_preferences, rotation_warnings


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
    assignment = capture()
    # Toplamdan ödün vermeden esnek izin, günlük dağılım, eş/kıdem tercihleri.
    model.Add(total == best_total)
    secondary = []
    soft = []
    for t in range(1,n+1):
        daily = sum(x24[d,t]+x16[d,t] for d in docs)
        dev = model.NewIntVar(0,n*len(docs),f'daily_dev_{t}')
        model.AddAbsEquality(dev, n*daily-best_total)
        secondary.append(dev*10)
        for d in docs:
            if manual.get(f'{d}_{t}') == 'S':
                soft.append(x24[d,t]+x16[d,t])
        seniors=[d for d in docs if data.get('seniority',{}).get(d)=='Kıdemli']
        mids=[d for d in docs if data.get('seniority',{}).get(d)=='Orta']
        if seniors and mids:
            diff=model.NewIntVar(0,len(docs),f'seniority_{t}')
            model.AddAbsEquality(diff,sum(x24[d,t] for d in seniors)-sum(x24[d,t] for d in mids))
            secondary.append(diff)
    valid_pairs=[p for p in data.get('couples',[]) if len(p)==2 and p[0] in docs and p[1] in docs]
    for i,(a,b) in enumerate(valid_pairs):
        for t in range(1,n+1):
            diff=model.NewBoolVar(f'pair_{i}_{t}')
            model.AddAbsEquality(diff,x24[a,t]+x16[a,t]-x24[b,t]-x16[b,t])
            secondary.append(diff*2)
    # Bir S ihlali, diğer ikincil maliyetlerin tamamından daha ağırdır.
    bound = 10*n*n*len(docs)+n*len(docs)+2*n*len(valid_pairs)+1
    rotation = [d for d in docs if d in data.get('rotation_doctors', [])]
    secondary.extend(add_rotation_preferences(
        model, docs, rotation, data['year'], data['month'], x24, x16,
    ))
    # Yeni tercihlerin toplamı da S izninin önceliğini düşürmemeli.
    bound += 100*n*(max(0,len(rotation)-1)+len(rotation))
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
    rotation_notes = rotation_warnings(
        rotation, data['year'], data['month'],
        {d: [t for t in range(1,n+1) if assignment[d,t]] for d in rotation},
    )
    return {'status':'OK','rows':rows,'stats':stats,'target':target,'assigned':best_total,
            'proven':proven,'violations':violations,'rotation_warnings':rotation_notes}


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
    warnings = [f'S izni: {v}' for v in result['violations']] + list(result.get('rotation_warnings', []))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        pd.DataFrame(summary, columns=['Alan', 'Değer']).to_excel(writer, sheet_name='Ozet', index=False)
        pd.DataFrame(daily).to_excel(writer, sheet_name='Gunluk Dagilim', index=False)
        pd.DataFrame(result['stats']).to_excel(writer, sheet_name='Kisi Bazinda', index=False)
        pd.DataFrame(schedule).to_excel(writer, sheet_name='Ornek Cizelge', index=False)
        if warnings:
            pd.DataFrame({'Uyarılar': warnings}).to_excel(writer, sheet_name='Uyarilar', index=False)
        writer.sheets['Ornek Cizelge'].set_column(2, 3, 40)
    return buf.getvalue()


def render(st, rest_days, calc_time, month_names):
    import pandas as pd
    ss=st.session_state
    st.subheader('🔎 Ön İnceleme — Aylık Nöbet Dağılımı')
    st.info('Kota & Kıdem ile İzin & İstekler sekmelerindeki girişlerinizi kaydedin. Günlük ihtiyaç girmeniz gerekmez. Her gün en fazla 2 kişi 16 saat çalışır.')
    st.caption('Önce yazılabilen toplam nöbet sayısı en yüksek tutulur; ardından esnek izinler ve günlük denge gözetilir. Kotalar aşılmaz. Bu tablo tüm ay için tek bir uygulanabilir dağılımdır; günlerin bağımsız maksimumları değildir.')
    st.caption('Rotasyon seçimleri de değerlendirilir: mümkün olduğunca farklı günler ve kişi başına ayda en fazla 2 cumartesi/pazar nöbeti hedeflenir. Bu esnek tercihler toplam nöbet sayısını azaltmaz.')
    data={'docs':list(ss.doctors),'year':int(ss.year),'month':int(ss.month),'rest':int(rest_days),
          'q24':dict(ss.quotas_24h),'q16':dict(ss.quotas_16h),'manual':dict(ss.manual_constraints),
          'seniority':dict(ss.seniority),'couples':list(ss.couples),
          'rotation_doctors':list(ss.get('rotation_doctors',[]))}
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
    if result['violations']:
        with st.expander('Esnek izin (S) günlerine yazılan nöbetler',expanded=True):
            for line in result['violations']:
                st.write(line)
    if result.get('rotation_warnings'):
        with st.expander('Rotasyon tercihleri — ön incelemede karşılanamayanlar',expanded=True):
            st.caption('Bu uyarılar ön incelemedeki örnek dağılıma aittir. Ana çizelgede kişiler ve uyarılar farklı olabilir.')
            for line in result['rotation_warnings']:
                st.warning(line)
    st.caption('Günlük ihtiyaçlara aktarım yalnızca sayıları aktarır. Ana çizelge motoru farklı kişiler seçebilir; ana motordaki kotalar mevcut sürümde esnek hedeftir.')
