"""Rotasyon tercihleri: zorunlu nöbet kurallarını değiştirmez."""
import calendar
from datetime import date


def _month_days(year, month):
    return range(1, calendar.monthrange(year, month)[1] + 1)


def _spread_penalties(model, group, days, x24, x16, tag):
    """Aynı gruptan birden fazla kişinin aynı güne gelmesini cezalandırır."""
    if len(group) <= 1:
        return []
    penalties = []
    for t in days:
        excess = model.NewIntVar(0, len(group) - 1, f'{tag}_overlap_{t}')
        model.AddMaxEquality(excess, [0, sum(x24[d, t] + x16[d, t] for d in group) - 1])
        penalties.append(excess * 100)
    return penalties


def _same_day_warnings(group, year, month, assignments, label):
    selected = [d for d in assignments if d in group]
    warnings = []
    for t in _month_days(year, month):
        same_day = [d for d in selected if t in assignments[d]]
        if len(same_day) > 1:
            warnings.append(f'{t:02d}.{month:02d}.{year}: {label}: {", ".join(same_day)}.')
    return warnings


def add_rotation_preferences(model, docs, selected, year, month, x24, x16):
    rotation = [d for d in docs if d in selected]
    if not rotation:
        return []
    days = _month_days(year, month)
    weekends = [t for t in days if date(year, month, t).weekday() >= 5]
    # Mevcut kota (500) ve esnek izin (5000) ağırlıkları korunur.
    # Rotasyon tercihleri sosyal/dağılım hedeflerine benzer esnek hedeflerdir.
    penalties = _spread_penalties(model, rotation, days, x24, x16, 'rotation')
    for d in rotation:
        excess = model.NewIntVar(0, len(weekends), f'rotation_weekend_{d}')
        model.AddMaxEquality(excess, [0, sum(x24[d, t] + x16[d, t] for t in weekends) - 2])
        penalties.append(excess * 100)
    return penalties


def rotation_warnings(selected, year, month, assignments):
    warnings = _same_day_warnings(selected, year, month, assignments,
                                  'Rotasyondaki kişiler aynı güne yazıldı')
    rotation = [d for d in assignments if d in selected]
    for d in rotation:
        count = sum(date(year, month, t).weekday() >= 5 for t in assignments[d])
        if count > 2:
            warnings.append(f'{d}: {count} hafta sonu nöbeti yazıldı (hedef en fazla 2).')
    return warnings


def add_incoming_preferences(model, docs, selected, year, month, x24, x16):
    """Rotasyona gelenler: her gün gruptan mümkün olduğunca tek kişi."""
    incoming = [d for d in docs if d in selected]
    return _spread_penalties(model, incoming, _month_days(year, month), x24, x16, 'incoming')


def incoming_warnings(selected, year, month, assignments):
    return _same_day_warnings(selected, year, month, assignments,
                              'Rotasyona gelenler aynı güne yazıldı')
