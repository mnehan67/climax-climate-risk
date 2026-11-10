"""Unit tests for the pipeline algorithms, finance engine and agent.   python3 -m unittest discover -s tests -v"""
import sys, unittest, pathlib
import numpy as np
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import core  # noqa: E402


class Algorithms(unittest.TestCase):
    def test_mndwi_sign(self):
        g = np.array([[0.1, 0.1]]); s = np.array([[0.02, 0.3]])
        m = core.mndwi(g, s)
        self.assertGreater(m[0, 0], 0); self.assertLess(m[0, 1], 0)

    def test_otsu_separates_bimodal(self):
        rng = np.random.default_rng(1)
        v = np.concatenate([rng.normal(-0.4, 0.05, 5000), rng.normal(0.5, 0.05, 1000)])
        t = core.otsu(v)
        self.assertTrue(-0.25 < t < 0.35, t)

    def test_priority_flood_fills_pit(self):
        dem = np.full((7, 7), 5.0); dem[3, 3] = 1.0
        f = core.priority_flood(dem)
        self.assertAlmostEqual(f[3, 3], 5.0); self.assertTrue((f >= dem).all())

    def test_priority_flood_keeps_slope(self):
        dem = np.tile(np.arange(6, dtype=float), (6, 1))
        self.assertTrue(np.allclose(core.priority_flood(dem), dem))

    def test_persistence_lower_bound_and_permanent_water(self):
        pre_w = np.array([[True, False, False]]); pre_v = np.ones((1, 3), bool)
        wet = np.array([[[True, True, True]], [[True, True, False]], [[True, False, False]]])
        val = np.ones_like(wet)
        p = core.persistence(pre_w, pre_v, wet, val, [1, 6, 11])
        self.assertFalse(p["flooded"][0, 0])            # permanent water excluded
        self.assertEqual(p["last_wet_day"][0, 1], 6)
        self.assertEqual(p["last_wet_day"][0, 2], 1)

    def test_persistence_ignores_cloudy_obs(self):
        pre_w = np.zeros((1, 1), bool); pre_v = np.ones((1, 1), bool)
        wet = np.array([[[True]], [[True]]]); val = np.array([[[True]], [[False]]])
        p = core.persistence(pre_w, pre_v, wet, val, [1, 6])
        self.assertEqual(p["last_wet_day"][0, 0], 1)

    def test_fwdet_depth_positive_in_bowl(self):
        yy, xx = np.mgrid[0:21, 0:21]
        dem = ((yy - 10) ** 2 + (xx - 10) ** 2) / 40.0
        flood = dem < 1.0
        d = core.fwdet_depth(flood, dem.astype("float32"), cap=5)
        self.assertGreater(d[10, 10], 0.5); self.assertEqual(d[0, 0], 0)

    def test_confusion_iou(self):
        a = np.array([[1, 1, 0, 0]], bool); b = np.array([[1, 0, 1, 0]], bool)
        m = core.confusion(a, b, np.ones_like(a))
        self.assertAlmostEqual(m["iou"], 1 / 3, places=3)

    def test_damage_curve_monotonic(self):
        d = core.damage_fraction([0, 0.25, 0.5, 1, 2, 6, 9])
        self.assertTrue(np.all(np.diff(d) >= 0)); self.assertEqual(d[0], 0); self.assertEqual(d[-1], 1)

    def test_building_metrics(self):
        rings = np.array([[1, 1, 2, 2]]); flooded = np.array([[True, False, False, False]])
        days = np.array([[6.0, 0, 0, 0]]); depth = np.array([[0.4, 0, 0, 0]]); pred = np.zeros((1, 4), bool)
        m = core.building_metrics(rings, 2, flooded, days, depth, pred)
        self.assertTrue(m[0]["flooded"]); self.assertEqual(m[0]["days"], 6); self.assertFalse(m[1]["flooded"])


class EngineAndAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import engine
        if not engine.available():
            from pipeline import make_test_data
            make_test_data.main()

    def test_zero_beta_zero_depth_means_no_pd_change(self):
        import engine
        s = engine.stress({"beta": 0})
        for r in s["loans"]:
            self.assertAlmostEqual(r["pd_stress_pct"], r["pd_pct"], places=6)

    def test_stress_monotonic_in_persistence(self):
        import engine
        a = engine.stress({"persist_mult": 1.0})["portfolio"]["delta_el"]
        b = engine.stress({"persist_mult": 2.0})["portfolio"]["delta_el"]
        self.assertGreaterEqual(b, a)

    def test_unflooded_loans_have_zero_delta(self):
        import engine
        for r in engine.stress()["loans"]:
            if r["channel"] == "NONE":
                self.assertEqual(r["delta_el"], 0)

    def test_param_limits(self):
        import engine
        with self.assertRaises(ValueError):
            engine.stress({"beta": 9})

    def test_loans_blind_to_flood(self):
        import json
        d = json.loads((ROOT / "data/generated/loans.json").read_text())
        self.assertIn("blind to flood", d["rule"])

    def test_agent_offline_arabic(self):
        import agent
        r = agent.ask_offline("أي القروض المرهونة بقيت تحت الماء أكثر من ٥ أيام؟", "alquoz", None)
        self.assertEqual(r["steps"][0]["tool"], "query_loans")
        self.assertEqual(r["steps"][0]["input"]["min_days"], 5.0)
        self.assertRegex(r["answer"], "[؀-ۿ]")

    def test_agent_offline_validation(self):
        import agent
        r = agent.ask_offline("how accurate is the forecast", "dxb", None)
        self.assertEqual(r["steps"][0]["tool"], "get_validation")

    def test_agent_never_invents_loan(self):
        import agent
        r = agent.ask_offline("explain SME-999", "alquoz", None)
        self.assertIn("unknown", r["answer"])

    def test_memo_contains_disclaimers(self):
        import memo
        h = memo.build()
        self.assertIn("synthetic", h.lower()); self.assertIn("not IFRS 9", h)


if __name__ == "__main__":
    unittest.main()
