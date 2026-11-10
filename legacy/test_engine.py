import unittest,sys,urllib.request,subprocess,os,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import summarize,haversine,load_loans,SITES,match_point
class TestEngine(unittest.TestCase):
 def test_inventory(self):
  d=summarize();self.assertGreaterEqual(d['summary']['loans'],70);self.assertTrue(all(x['data_class'].startswith('SYNTHETIC') for x in d['loans']));self.assertEqual(d['summary']['loans'],len(load_loans()))
 def test_mechanics(self):
  x=summarize(1,0);y=summarize(2,10);self.assertEqual(x['summary']['delta'],0);self.assertGreater(y['summary']['delta'],0)
  z=summarize(3,10);self.assertGreater(z['summary']['delta'],y['summary']['delta'])
 def test_formula_case(self):
  d=summarize(2,10)
  for x in d['loans']:
   p=x['pd_pct']/100;lg=x['lgd_pct']/100
   ps=min(1,p*2) if x['ops'] else p
   ls=min(1,lg+.1) if x['coll'] else lg
   want=round(x['ead_aed']*(ps*ls-p*lg))
   self.assertLessEqual(abs(want-x['delta_ecl']),1,x['loan_id'])
 def test_spatial(self):
  for s in SITES:
   hits=match_point(s['lat'],s['lon']);self.assertIn(s['id'],[x['site_id'] for x in hits]);self.assertEqual(round(haversine(s['lat'],s['lon'],s['lat'],s['lon'])),0)
 def test_accuracy_provenance(self):
  d=summarize();self.assertIsNone(d['assumptions']['accuracy']);self.assertIsNone(d['assumptions']['depth_m']);self.assertIn('no depth raster',d['method']['limit'].lower());self.assertEqual(d['event_date'],'2024-04-16')
 def test_geographic_bounds(self):
  for x in load_loans():
   self.assertTrue(24<x['borrower_lat']<26);self.assertTrue(54<x['borrower_lon']<57)
 def test_field_validation(self):
  with self.assertRaises(ValueError):summarize(0,2)
  with self.assertRaises(ValueError):summarize(10,2)
  with self.assertRaises(ValueError):summarize(2,40)
 def test_reproducibility(self):
  a=summarize();b=summarize();self.assertEqual(a['loans'],b['loans']);self.assertEqual(a['summary'],b['summary'])
if __name__=='__main__':unittest.main()
