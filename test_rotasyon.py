import unittest
from ortools.sat.python import cp_model
from nobet_tani import build_rules
import importlib.util


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('nobet_rotasyon'),
                             'Rotasyon tercihleri henüz uygulanmadı')
        from nobet_rotasyon import add_rotation_preferences, rotation_warnings
        self.add = add_rotation_preferences
        self.warnings = rotation_warnings

    def solve(self, selected, needs24, needs16, manual=None):
        model = cp_model.CpModel()
        docs = ['A', 'B', 'C']
        daily24 = {t: needs24.get(t, 0) for t in range(1, 31)}
        x24, x16, _, _, _ = build_rules(model, docs, 30, 1, daily24, needs16, manual or {})
        penalties = self.add(model, docs, selected, 2026, 9, x24, x16)
        model.Minimize(sum(penalties))
        solver = cp_model.CpSolver()
        self.assertEqual(solver.Solve(model), cp_model.OPTIMAL)
        assignments = {d: [t for t in range(1, 31)
                           if solver.Value(x24[d, t]) + solver.Value(x16[d, t])]
                       for d in docs}
        return assignments, penalties, solver

    def test_rotation_people_spread_across_days_and_shift_types(self):
        a, _, solver = self.solve(['A', 'B'], {1: 1, 3: 1}, {1: 1, 3: 1})
        self.assertFalse(set(a['A']) & set(a['B']))
        self.assertEqual(solver.ObjectiveValue(), 0)

    def test_weekend_limit_counts_both_shift_types(self):
        a, _, _ = self.solve(['A'], {5: 1, 12: 1}, {19: 1},
                             {'A_5': '24', 'A_12': '24'})
        self.assertEqual(a['A'], [5, 12])

    def test_forced_exceptions_still_solve_and_are_reported(self):
        a, _, solver = self.solve(['A', 'B'], {5: 1, 12: 1}, {5: 1, 19: 1},
                                 {'A_5': '24', 'B_5': '16', 'A_12': '24', 'A_19': '16'})
        self.assertGreater(solver.ObjectiveValue(), 0)
        warnings = self.warnings(['A', 'B'], 2026, 9, a)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any('05.09.2026' in w and 'A' in w and 'B' in w for w in warnings))
        self.assertTrue(any('A' in w and '3' in w for w in warnings))

    def test_empty_selection_does_not_add_preferences(self):
        _, penalties, _ = self.solve([], {5: 1}, {})
        self.assertEqual(penalties, [])
        self.assertEqual(self.warnings([], 2026, 9, {'A': [5, 12, 19]}), [])

    def test_friday_not_counted_and_two_weekend_days_allowed(self):
        self.assertEqual(self.warnings(['A'], 2026, 9, {'A': [4, 5, 12]}), [])


class IncomingTests(unittest.TestCase):
    def setUp(self):
        from nobet_rotasyon import add_incoming_preferences, incoming_warnings
        self.add = add_incoming_preferences
        self.warnings = incoming_warnings

    def solve(self, selected, needs24, needs16, manual=None):
        model = cp_model.CpModel()
        docs = ['A', 'B', 'C']
        daily24 = {t: needs24.get(t, 0) for t in range(1, 31)}
        x24, x16, _, _, _ = build_rules(model, docs, 30, 1, daily24, needs16, manual or {})
        penalties = self.add(model, docs, selected, 2026, 9, x24, x16)
        model.Minimize(sum(penalties))
        solver = cp_model.CpSolver()
        self.assertEqual(solver.Solve(model), cp_model.OPTIMAL)
        assignments = {d: [t for t in range(1, 31)
                           if solver.Value(x24[d, t]) + solver.Value(x16[d, t])]
                       for d in docs}
        return assignments, penalties, solver

    def test_incoming_people_spread_across_days(self):
        a, _, solver = self.solve(['A', 'B'], {1: 1, 3: 1}, {1: 1, 3: 1})
        self.assertFalse(set(a['A']) & set(a['B']))
        self.assertEqual(solver.ObjectiveValue(), 0)
        self.assertEqual(self.warnings(['A', 'B'], 2026, 9, a), [])

    def test_forced_same_day_still_solves_and_is_reported(self):
        a, _, solver = self.solve(['A', 'B'], {5: 2}, {}, {'A_5': '24', 'B_5': '24'})
        self.assertEqual(set(a['A']) & set(a['B']), {5})
        self.assertGreater(solver.ObjectiveValue(), 0)
        warnings = self.warnings(['A', 'B'], 2026, 9, a)
        self.assertEqual(len(warnings), 1)
        self.assertIn('Rotasyona gelenler', warnings[0])
        self.assertIn('05.09.2026', warnings[0])

    def test_single_or_empty_selection_does_not_add_preferences(self):
        _, penalties, _ = self.solve(['A'], {5: 1}, {})
        self.assertEqual(penalties, [])
        self.assertEqual(self.warnings([], 2026, 9, {'A': [5, 12, 19]}), [])


if __name__ == '__main__':
    unittest.main()
