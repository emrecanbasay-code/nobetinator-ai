import unittest
from ortools.sat.python import cp_model
from nobet_tani import build_rules, diagnose, day_capacity, show_failure
from kurulumu_uygula import transform


class Tests(unittest.TestCase):
    def solve(self, docs, n, rest, n24, n16, manual):
        model = cp_model.CpModel()
        build_rules(model, docs, n, rest, n24, n16, manual)
        solver = cp_model.CpSolver()
        return solver.Solve(model)

    def test_daily_shortage(self):
        r = diagnose(['A','B','C'], 1, 2, {1:2}, {1:0}, {'A_1':'X','B_1':'X'})
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertEqual(r['daily'][0]['total_upper_bound'], 1)
        self.assertTrue(r['core'])

    def test_fixed_rest(self):
        r = day_capacity(['A'], 14, 2, {d: int(d in (11,13)) for d in range(1,15)}, {}, {'A_11':'24'})
        self.assertEqual(r[0]['day'], 13)
        self.assertIn('dinlenme', str(r[0]['excluded']))

    def test_joint_days(self):
        r = diagnose(['A'], 2, 1, {1:1,2:1}, {}, {})
        self.assertFalse(r['daily'])
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertEqual(r['days'], [1,2])

    def test_month_end(self):
        needs = {d: int(d in (29,31)) for d in range(1,32)}
        self.assertEqual(self.solve(['A'],31,3,needs,{}, {'A_29':'24','A_31':'16'}), cp_model.INFEASIBLE)
        # Doğru vardiya ihtiyaçlarıyla da dinlenme çakışması kanıtlanmalı.
        needs[31] = 0
        self.assertEqual(self.solve(['A'],31,3,needs,{31:1}, {'A_29':'24','A_31':'16'}), cp_model.INFEASIBLE)

    def test_feasible_soft_leave(self):
        self.assertIn(self.solve(['A'],1,2,{1:1},{},{'A_1':'S'}), (cp_model.FEASIBLE,cp_model.OPTIMAL))

    def test_sixteen_next_day(self):
        self.assertEqual(self.solve(['A'],2,2,{1:0,2:0},{1:1,2:1},{}), cp_model.INFEASIBLE)

    def test_sixteen_alternate_allowed(self):
        self.assertIn(self.solve(['A'],3,3,{1:0,2:0,3:0},{1:1,3:1},{}), (cp_model.FEASIBLE,cp_model.OPTIMAL))

    def test_type_shortage(self):
        r = day_capacity(['A','B'],1,2,{1:1},{1:1},{'A_1':'16','B_1':'16'})
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['eligible24'],[])

    def test_unknown_message(self):
        class UI:
            def warning(self, msg): self.msg=msg
        ui=UI()
        show_failure(ui, cp_model.UNKNOWN, None, [], 1, 1, {}, {}, {})
        self.assertIn('kanıtlanmadı', ui.msg)

    def test_refuse_wrong_source(self):
        with self.assertRaises(ValueError): transform('print(123)')

if __name__ == '__main__': unittest.main()
