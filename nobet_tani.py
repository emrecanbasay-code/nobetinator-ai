"""Nobetinator: sabit kurallar, gunluk kapasite ve kanitli celiski tanisi."""
import time
from ortools.sat.python import cp_model


def build_rules(model, docs, num_days, rest_days, needs24, needs16, manual,
                diagnostic=False, free_capacity=False):
    x24, x16, soft, labels = {}, {}, {}, {}
    guards = []

    def rule(expr, text, days):
        guard = model.NewBoolVar(f'rule_{len(guards)}')
        model.Add(expr).OnlyEnforceIf(guard)
        guards.append(guard)
        labels[guard.Index()] = {'text': text, 'days': list(days)}
        if diagnostic:
            model.AddAssumption(guard)
        else:
            model.Add(guard == 1)

    for i, doc in enumerate(docs):
        for day in range(1, num_days + 1):
            x24[doc, day] = model.NewBoolVar(f'x24_{i}_{day}')
            x16[doc, day] = model.NewBoolVar(f'x16_{i}_{day}')
            model.Add(x24[doc, day] + x16[doc, day] <= 1)
    for day in range(1, num_days + 1):
        if free_capacity:
            rule(sum(x16[doc, day] for doc in docs) <= 1,
                 f'{day}. gün: en fazla 1 kişi 16 saat nöbet tutabilir.', [day])
            continue
        for variables, needs, hours, default in [(x24, needs24, 24, 1), (x16, needs16, 16, 0)]:
            count = int(needs.get(day, default))
            rule(sum(variables[doc, day] for doc in docs) == count,
                 f'{day}. gün: {hours} saat nöbet için tam {count} kişi gerekli.', [day])
    for doc in docs:
        for day in range(1, num_days):
            rule(x24[doc, day] + x16[doc, day] + x24[doc, day+1] + x16[doc, day+1] <= 1,
                 f'{doc}: {day} ve {day+1}. günlerde peş peşe çalışamaz.', [day, day+1])
        for day in range(1, num_days + 1):
            # Ay sonundaki kalan günler de korunur.
            for later in range(day+2, min(num_days, day+rest_days)+1):
                rule(x24[doc, day] + x24[doc, later] + x16[doc, later] <= 1,
                     f'{doc}: {day}. gün 24 saat nöbet tutarsa {later}. gün dinlenmeli '
                     f'(dinlenme ayarı: {rest_days} gün).', [day, later])
            value = manual.get(f'{doc}_{day}', '')
            if value == 'X':
                rule(x24[doc, day] + x16[doc, day] == 0,
                     f'{doc}: {day}. gün kesin izinli (X).', [day])
            elif value in ('24', '16'):
                target = x24 if value == '24' else x16
                rule(target[doc, day] == 1,
                     f'{doc}: {day}. gün sabit {value} saat nöbeti var.', [day])
            elif value == 'S' and not diagnostic:
                violation = model.NewBoolVar(f'soft_{len(soft)}')
                model.Add(violation == x24[doc, day] + x16[doc, day])
                soft[doc, day] = violation
    return x24, x16, soft, labels, guards


def day_capacity(docs, num_days, rest_days, needs24, needs16, manual):
    """Sabit kayıtlar üzerinden üst sınır. Küresel atanabilirlik iddiası değildir."""
    failures = []
    for day in range(1, num_days+1):
        eligible = {24: [], 16: []}
        excluded = []
        for doc in docs:
            reasons = {24: [], 16: []}
            current = manual.get(f'{doc}_{day}', '')
            for hours in (24, 16):
                if current == 'X':
                    reasons[hours].append('kesin izin (X)')
                elif current in ('24', '16') and int(current) != hours:
                    reasons[hours].append(f'aynı gün sabit {current} saat nöbeti')
                for fixed_day in range(1, num_days+1):
                    fixed = manual.get(f'{doc}_{fixed_day}', '')
                    if fixed not in ('24', '16') or fixed_day == day:
                        continue
                    if abs(fixed_day-day) == 1:
                        reasons[hours].append(f'{fixed_day}. gün sabit nöbeti; ardışık gün yasağı')
                    elif fixed_day < day and fixed == '24' and day-fixed_day <= rest_days:
                        reasons[hours].append(f'{fixed_day}. günkü 24 saat nöbetinden sonra dinlenme')
                    elif fixed_day > day and hours == 24 and fixed_day-day <= rest_days:
                        reasons[hours].append(f'24 saat atanırsa {fixed_day}. günkü sabit nöbetle dinlenme çakışır')
                if not reasons[hours]:
                    eligible[hours].append(doc)
            if reasons[24] or reasons[16]:
                parts = [f'{h}s: ' + '; '.join(dict.fromkeys(reasons[h])) for h in (24, 16) if reasons[h]]
                excluded.append(f'{doc} — ' + ' | '.join(parts))
        n24, n16 = int(needs24.get(day, 1)), int(needs16.get(day, 0))
        # İhtiyaç bulunmayan vardiya tipindeki adaylar toplamı şişirmemeli.
        union = set(eligible[24] if n24 else []) | set(eligible[16] if n16 else [])
        if n24 > len(eligible[24]) or n16 > len(eligible[16]) or n24+n16 > len(union):
            failures.append({'day': day, 'need24': n24, 'need16': n16,
                             'eligible24': eligible[24], 'eligible16': eligible[16],
                             'total_upper_bound': len(union), 'excluded': excluded})
    return failures


def diagnose(docs, num_days, rest_days, needs24, needs16, manual, seconds=12):
    report = {'daily': day_capacity(docs, num_days, rest_days, needs24, needs16, manual),
              'core': [], 'days': [], 'status': 'UNKNOWN'}
    model = cp_model.CpModel()
    *_, labels, guards = build_rules(model, docs, num_days, rest_days, needs24, needs16, manual, True)
    deadline = time.monotonic() + seconds
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = max(0.01, seconds * .65)
    status = solver.Solve(model)
    report['status'] = solver.StatusName(status)
    if status != cp_model.INFEASIBLE:
        return report
    core = list(solver.SufficientAssumptionsForInfeasibility())
    by_index = {g.Index(): g for g in guards}
    # Yalnızca tekrar INFEASIBLE kanıtlanırsa çekirdek küçültülür.
    for candidate in list(core):
        remaining = deadline-time.monotonic()
        if remaining <= .05:
            break
        if candidate not in core:
            continue
        trial = [i for i in core if i != candidate]
        model.ClearAssumptions()
        model.AddAssumptions([by_index[i] for i in trial])
        solver.parameters.max_time_in_seconds = min(.3, remaining)
        if solver.Solve(model) == cp_model.INFEASIBLE:
            core = list(solver.SufficientAssumptionsForInfeasibility())
    report['core'] = [labels[i]['text'] for i in core]
    report['days'] = sorted({d for i in core for d in labels[i]['days']})
    return report


def show_failure(st, status, model, docs, num_days, rest_days, needs24, needs16, manual):
    if status == cp_model.UNKNOWN:
        st.warning('Süre içinde çözüm bulunamadı. Çizelgenin imkânsız olduğu kanıtlanmadı. Hesaplama süresini artırabilirsiniz.')
        return
    if status == cp_model.MODEL_INVALID:
        st.error('Modelde teknik hata var. Bu, izinlerin çakıştığı anlamına gelmez.')
        st.code(model.Validate() or 'Çözücü model doğrulamasını reddetti.')
        return
    if status != cp_model.INFEASIBLE:
        st.error(f'Beklenmeyen çözücü durumu: {status}')
        return
    st.error('Mevcut kuralların tamamını sağlayan çizelge oluşturulamıyor.')
    with st.spinner('Sorunlu günler ve çelişen kurallar araştırılıyor...'):
        result = diagnose(docs, num_days, rest_days, needs24, needs16, manual)
    for item in result['daily']:
        st.error(f"{item['day']}. gün: ihtiyaç karşılanamıyor. "
                 f"İhtiyaç: {item['need24']} kişi 24s + {item['need16']} kişi 16s. "
                 f"Sabit kayıtlar ve dinlenme kurallarına göre aday sayısı en fazla {item['total_upper_bound']}.")
        with st.expander(f"{item['day']}. gün: kim neden atanamıyor?", expanded=True):
            st.write('24s adayları: ' + (', '.join(item['eligible24']) or 'Yok'))
            st.write('16s adayları: ' + (', '.join(item['eligible16']) or 'Yok'))
            for line in item['excluded']:
                st.write('• ' + line)
    if result['core']:
        st.warning('Birlikte çeliştiği kanıtlanan kuralların ilgili günleri: ' + ', '.join(map(str, result['days'])))
        with st.expander('Çözümsüzlüğe yol açan kural grubu', expanded=True):
            for line in result['core']:
                st.write('• ' + line)
            st.caption('Bu kurallar birlikte sağlanamıyor. Liste bütün sorunları veya en küçük çelişki grubunu göstermeyebilir. Tek bir kuralın değiştirilmesi tüm çizelgeyi çözmeyebilir.')
    elif result['status'] in ('OPTIMAL', 'FEASIBLE'):
        st.warning('Temel nöbet kuralları için çözüm bulundu. Ana modeldeki ek sınırlamalar veya yardımcı değişken sınırları incelenmeli.')
    elif not result['daily']:
        st.info('Çözümsüzlük ana modelde kanıtlandı; ayrıntılı tanılama süresinde kişi/gün açıklaması elde edilemedi.')
    st.caption('Kesin izinler ve dinlenme kuralları otomatik değiştirilmedi. Esnek izinler ve hedef kotalar bu tanılama modelinde zorunlu kural değildir.')
