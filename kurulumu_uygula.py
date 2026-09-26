"""Paylasilan app.py surumune tani ekler; orijinali yedekler."""
import ast
from pathlib import Path
import shutil
import sys
from datetime import datetime


def transform(source):
    if 'from nobet_tani import build_rules, show_failure' in source:
        raise ValueError('Tanılama zaten eklenmiş; tekrar uygulanmadı.')
    start_marker = '            # 1. TEMEL DEĞİŞKENLER'
    end_marker = '            status_text.text("Evlilik ve Sosyal kurallar işleniyor...")'
    fail_marker = '            else:\n                st.error("🚨 Çözüm Bulunamadı! (INFEASIBLE)")'
    for marker in (start_marker, end_marker, fail_marker):
        if source.count(marker) != 1:
            raise ValueError('app.py beklenen sürümle eşleşmiyor; hiçbir değişiklik yapılmadı. Eksik/tekrarlı bölüm: ' + marker.strip())
    first, end = source.index(start_marker), source.index(end_marker)
    if first >= end:
        raise ValueError('Model bölümlerinin sırası beklenenden farklı.')
    new_rules = '''            # Temel kurallar ve tanılama aynı kural üreticisini kullanır.
            x24, x16, soft_violations, _, _ = build_rules(
                model, docs, num_days, rest_days_24h,
                st.session_state.daily_needs_24h,
                st.session_state.daily_needs_16h,
                st.session_state.manual_constraints,
            )

'''
    source = source[:first] + new_rules + source[end:]
    # AST ile yalnızca çözücünün başarısızlık dalını değiştir.
    tree = ast.parse(source)
    failures = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                and ast.get_source_segment(source, n.test) == 'status in [cp_model.OPTIMAL, cp_model.FEASIBLE]']
    if len(failures) != 1 or not failures[0].orelse:
        raise ValueError('Çözücü sonuç dalı bulunamadı; dosya değiştirilmedi.')
    branch = failures[0].orelse
    lines = source.splitlines(keepends=True)
    new_failure = '''                show_failure(
                    st, status, model, docs, num_days, rest_days_24h,
                    st.session_state.daily_needs_24h,
                    st.session_state.daily_needs_16h,
                    st.session_state.manual_constraints,
                )
'''
    lines[branch[0].lineno-1:branch[-1].end_lineno] = [new_failure]
    source = ''.join(lines)
    # Python dosyasının başına eklenmez: varsa future importlarını korur.
    anchor = 'from ortools.sat.python import cp_model'
    if source.count(anchor) != 1:
        raise ValueError('OR-Tools importu bulunamadı.')
    source = source.replace(anchor, anchor + '\nfrom nobet_tani import build_rules, show_failure', 1)
    ast.parse(source)
    return source


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else 'app.py').resolve()
    module = Path(__file__).resolve().with_name('nobet_tani.py')
    text = target.read_text(encoding='utf-8-sig')
    updated = transform(text)
    destination = target.with_name('nobet_tani.py')
    if destination.exists() and destination.resolve() != module.resolve() and destination.read_bytes() != module.read_bytes():
        raise ValueError('Hedefte farklı bir nobet_tani.py var; üzerine yazılmadı.')
    backup = target.with_name('app_onceki_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.py.bak')
    shutil.copy2(target, backup)
    if destination.resolve() != module.resolve():
        shutil.copy2(module, destination)
    temporary = target.with_name('app_tani_gecici.py')
    temporary.write_text(updated, encoding='utf-8')
    temporary.replace(target)
    print('Tamamlandı. Güncellenen dosya:', target)
    print('Önceki sürüm:', backup)
    print('GitHub kullanıyorsanız app.py ve nobet_tani.py dosyalarını birlikte yükleyin.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Kurulum tamamlanamadı:', exc)
        sys.exit(1)
