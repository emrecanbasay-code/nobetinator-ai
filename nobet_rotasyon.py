"""Rotasyon tercihleri: zorunlu nöbet kurallarını değiştirmez."""
import calendar
from datetime import date


def add_rotation_preferences(model, docs, selected, year, month, x24, x16):
    rotation = [d for d in docs if d in selected]
    if not rotation:
        return []
    days = range(1, calendar.monthrange(year, month)[1] + 1)
    weekends = [t for t in days if date(year, month, t).weekday() >= 5]
    penalties = []
    # Mevcut kota (500) ve esnek izin (5000) ağırlıkları korunur.
    # Rotasyon tercihleri sosyal/dağılım hedeflerine benzer esnek hedeflerdir.
    if len(rotation) > 1:
        for t in days:
            excess = model.NewIntVar(0, len(rotation) - 1, f'rotation_overlap_{t}')
            model.AddMaxEquality(excess, [0, sum(x24[d, t] + x16[d, t] for d in rotation) - 1])
            penalties.append(excess * 100)
    for d in rotation:
        excess = model.NewIntVar(0, len(weekends), f'rotation_weekend_{d}')
        model.AddMaxEquality(excess, [0, sum(x24[d, t] + x16[d, t] for t in weekends) - 2])
        penalties.append(excess * 100)
    return penalties


def rotation_warnings(selected, year, month, assignments):
    rotation = [d for d in assignments if d in selected]
    warnings = []
    for t in range(1, calendar.monthrange(year, month)[1] + 1):
        same_day = [d for d in rotation if t in assignments[d]]
        if len(same_day) > 1:
            warnings.append(f'{t:02d}.{month:02d}.{year}: Rotasyondaki kişiler aynı güne yazıldı: {", ".join(same_day)}.')
    for d in rotation:
        count = sum(date(year, month, t).weekday() >= 5 for t in assignments[d])
        if count > 2:
            warnings.append(f'{d}: {count} hafta sonu nöbeti yazıldı (hedef en fazla 2).')
    return warnings
