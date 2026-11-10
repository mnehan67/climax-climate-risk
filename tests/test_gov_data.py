"""DLD (Data.Dubai) loader: tolerant column detection, area matching, filters, and loan re-pricing."""
import csv, sys, tempfile, unittest, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import gov_data, loans  # noqa: E402


class GovData(unittest.TestCase):
    def make_csv(self):
        p = pathlib.Path(tempfile.mkdtemp()) / "dld.csv"
        rows = [
            ["transaction_id", "trans_group_en", "instance_date", "property_usage_en", "area_name_en", "procedure_area", "actual_worth", "meter_sale_price"],
            ["1", "Sales", "2023-05-01", "Residential", "Al Barsha South Fourth", "100", "1500000", "15000"],
            ["2", "Sales", "2023-05-02", "Commercial", "Al Qouz Industrial Second", "1000", "5000000", "5000"],
            ["3", "Mortgages", "2023-05-03", "Commercial", "Al Qouz Industrial Second", "1000", "9000000", "9000"],   # not a sale
            ["4", "Sales", "2015-01-01", "Commercial", "Al Qouz Industrial Second", "1000", "1000000", "1000"],   # too old
            ["5", "Sales", "2024-02-01", "Residential", "Al Furjan", "120", "1440000", "12000"],
            ["6", "Sales", "2024-02-01", "Residential", "Business Bay", "120", "3000000", "25000"],                # outside areas
            ["7", "Sales", "2024-02-01", "Commercial", "Al Garhoud", "200", "", ""],                                  # no price
        ]
        with open(p, "w", newline="") as f:
            csv.writer(f).writerows(rows)
        return p

    def test_loader(self):
        g = gov_data.load_dld([self.make_csv()])
        self.assertEqual(g["rows_used"], 3)
        self.assertEqual(g["by_aoi"]["alquoz"]["residential"], 15000)
        self.assertEqual(g["by_aoi"]["alquoz"]["commercial"], 5000)
        self.assertEqual(g["by_aoi"]["jebelali"]["all"], 12000)
        self.assertNotIn("dxb", g["by_aoi"])

    def test_loans_priced_from_dld(self):
        g = gov_data.load_dld([self.make_csv()])
        b = {"alquoz": [{"id": "w1", "use": "warehouse", "height": 9, "area_m2": 1000}]}
        ls = loans.make_loans(b, n=5, gov=g)
        for l in ls:
            self.assertEqual(l["collateral_value_source"], "DLD median AED/m² (Data.Dubai)")
            self.assertEqual(l["collateral_value_aed"], 5_000_000)   # 1000 m² x 5000 AED/m²

    def test_no_file_falls_back(self):
        ls = loans.make_loans({"alquoz": [{"id": "w1", "use": "warehouse", "height": 9, "area_m2": 1000}]}, n=3, gov=None)
        self.assertTrue(all(l["collateral_value_source"].startswith("synthetic") for l in ls))


if __name__ == "__main__":
    unittest.main()
