"""Gerçek rapor üretim bloğunun Excel çıktısını doğrular."""
import ast
import io
from pathlib import Path
import unittest
import pandas as pd


class ExportTests(unittest.TestCase):
    def test_rotation_and_leave_warnings_are_exported(self):
        tree = ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
        block = next(n for n in ast.walk(tree) if isinstance(n, ast.With)
                     and isinstance(n.items[0].context_expr, ast.Call)
                     and isinstance(n.items[0].context_expr.func, ast.Attribute)
                     and n.items[0].context_expr.func.attr == 'ExcelWriter'
                     and any(isinstance(c, ast.Constant) and c.value == 'Istatistik'
                             for c in ast.walk(n)))
        for leave in ([], ['A: esnek izin ihlali']):
            with self.subTest(leave=leave):
                buf = io.BytesIO()
                frame = pd.DataFrame({'Tarih':['1'], 'A':['24h']})
                kars = pd.DataFrame({'Personel':['A'], '01.09':['S→24']})
                scope = dict(pd=pd, buf=buf, df_list=frame, df_grid=frame, df_stat=frame,
                             df_kars=kars,
                             warnings=leave, rotation_notes=['A: 3 hafta sonu nöbeti'],
                             incoming_notes=['B: rotasyona gelenler aynı gün'],
                             num_days=1, docs=['A'])
                exec(compile(ast.Module(body=[block],type_ignores=[]),'app.py','exec'),scope)
                excel = pd.ExcelFile(io.BytesIO(buf.getvalue()))
                self.assertIn('Uyarilar',excel.sheet_names)
                self.assertEqual(pd.read_excel(excel,sheet_name='Uyarilar')['Uyarılar'].tolist(),
                                 leave + ['A: 3 hafta sonu nöbeti','B: rotasyona gelenler aynı gün'])
                self.assertIn('Istek Karsilastirma',excel.sheet_names)
                self.assertEqual(pd.read_excel(excel,sheet_name='Istek Karsilastirma')['01.09'].tolist(),
                                 ['S→24'])
