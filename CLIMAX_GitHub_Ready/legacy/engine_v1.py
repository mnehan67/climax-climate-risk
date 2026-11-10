"""CLIMAX STORM: spatial screening + transparent hypothetical credit stress.
This is NOT a calibrated property damage probability, hydrodynamic model, or IFRS 9 ECL.
"""
from __future__ import annotations
import csv, json, math, pathlib, random, statistics
ROOT=pathlib.Path(__file__).resolve().parent

SITES=[
 {'id':'jebelali','name':'Jebel Ali','label':'JEBEL ALI','lat':24.9863,'lon':55.0748,'radius_m':1100,'observation':'Satellite-visible water accumulation in the Jebel Ali area; not parcel damage','source_type':'Sentinel-2 / ESA','url':'https://www.esa.int/ESA_Multimedia/Images/2024/04/Dubai_floods_seen_from_space','source_date':'2024-04-17','scope':'regional optical image, no ground depth'},
 {'id':'alquoz','name':'Al Quoz 1','label':'AL QUOZ','lat':25.153,'lon':55.24,'radius_m':750,'observation':'Flooded industrial-area streets were reported','source_type':'The National','url':'https://www.thenationalnews.com/news/uae/2025/04/16/the-uae-like-youve-never-seen-it-before-and-after-aprils-unprecedented-storm-of-2024/','source_date':'2025-04-16 retrospective','scope':'reported locality, not a property footprint'},
 {'id':'airport','name':'Dubai International','label':'DXB AIRPORT','lat':25.2528,'lon':55.3657,'radius_m':1000,'observation':'Airport operations disrupted during heavy rain','source_type':'Dubai Airports','url':'https://media.dubaiairports.ae/dubai-airports-back-to-normal-operations/','source_date':'2024-04-23','scope':'airport-wide operational impacts'},
 {'id':'alfurjan','name':'Al Furjan','label':'AL FURJAN','lat':25.027,'lon':55.144,'radius_m':780,'observation':'Waterlogged streets documented in April 2024','source_type':'The National','url':'https://www.thenationalnews.com/news/uae/2024/04/17/aftermath-of-tuesdays-storms-in-abu-dhabi-and-dubai-in-pictures/','source_date':'2024-04-17','scope':'reported locality, not a property footprint'},
 {'id':'discovery','name':'Discovery Gardens','label':'DISCOVERY','lat':25.0405,'lon':55.1395,'radius_m':830,'observation':'Waterlogged routes reported days after the storm','source_type':'The National','url':'https://www.thenationalnews.com/news/uae/2024/04/22/dubai-flooding-the-aftermath-in-pictures/','source_date':'2024-04-22','scope':'reported locality, not a property footprint'},
 {'id':'albarsha','name':'Al Barsha','label':'AL BARSHA','lat':25.11,'lon':55.203,'radius_m':650,'observation':'Floodwater documented in streets','source_type':'The National','url':'https://www.thenationalnews.com/news/uae/2025/04/16/the-uae-like-youve-never-seen-it-before-and-after-aprils-unprecedented-storm-of-2024/','source_date':'2025-04-16 retrospective','scope':'reported locality, not a property footprint'},
 {'id':'mudon','name':'Mudon','label':'MUDON','lat':25.024,'lon':55.252,'radius_m':650,'observation':'Standing water reported in streets after the heavy rain','source_type':'DXB Rest','url':'https://dxbrest.ae/en/details.php?id=758','source_date':'2024-04-23','scope':'reported locality, not measured depth'},
 {'id':'warsan','name':'Warsan','label':'WARSAN','lat':25.154,'lon':55.445,'radius_m':650,'observation':'Waterlogged areas reported after the storm','source_type':'DXB Rest','url':'https://dxbrest.ae/en/details.php?id=758','source_date':'2024-04-23','scope':'reported locality, not measured depth'},
 {'id':'industrial','name':'Dubai Industrial City','label':'INDUSTRIAL','lat':24.845,'lon':55.171,'radius_m':1000,'observation':'Industrial activity disrupted in affected wider region','source_type':'Hong et al. 2026','url':'https://www.tandfonline.com/doi/full/10.1080/19475683.2026.2639768','source_date':'2026 study','scope':'study-level context only'}
]
SITE_BY_ID={s['id']:s for s in SITES}
METHOD={
 'id':'reported_locality_screening','label':'Location screening — not flood prediction',
 'event_date':'2024-04-16','image_date':'2024-04-17',
 'provenance':'ESA Copernicus Sentinel-2 false-colour optical scene, plus historical reports. Synthetic loan coordinates.',
 'limit':'No depth raster, surveyed damage, observed defaults, cadastral ownership, calibrated flood likelihood, or calibrated damage classifier. Visual rain and water are reenactments.',
 'formula':'EAD × stressed PD × stressed LGD − EAD × baseline PD × baseline LGD',
 'note':'The result is a one-period illustrative credit-loss sensitivity, NOT IFRS 9 ECL, capital impact, or an assessed loss.',
 'sources':[
  {'name':'ESA · Sentinel-2 17 April 2024','url':'https://www.esa.int/ESA_Multimedia/Images/2024/04/Dubai_floods_seen_from_space'},
  {'name':'MBZUAI · 2024 Dubai flood study','url':'https://staticcdn.mbzuai.ac.ae/mbzuaiwpprd01/2024/05/EmiratesAndOman_RainCaseStudy.pdf'},
  {'name':'NASA · April 2024 UAE rainfall','url':'https://science.nasa.gov/earth/earth-observatory/deluge-in-the-united-arab-emirates-152703/'},
  {'name':'NASA · Prithvi deployment limitations 2026','url':'https://ntrs.nasa.gov/citations/20260003287'},
  {'name':'CBUAE · Climate Financial Risk Intelligence brief','url':'https://rulebook.centralbank.ae/en/rulebook/article-4-risk-management'}
 ]}

def haversine(lat1,lon1,lat2,lon2):
 r=6371000.0;a1=math.radians(lat1);a2=math.radians(lat2);dlat=a2-a1;dlon=math.radians(lon2-lon1)
 a=math.sin(dlat/2)**2+math.cos(a1)*math.cos(a2)*math.sin(dlon/2)**2
 return 2*r*math.asin(min(1,math.sqrt(a)))

def load_loans():
 with (ROOT/'data'/'loans_base.csv').open(newline='',encoding='utf-8-sig') as f:
  rows=list(csv.DictReader(f))
 rng=random.Random(20240416)
 categories=['Logistics','Light industrial','Wholesale','Manufacturing','Food Distribution']
 for i in range(18):
  lat,lon=SITE_BY_ID['jebelali']['lat'],SITE_BY_ID['jebelali']['lon']
  dr=lambda:(rng.random()-.5)*.017
  rows.append({'loan_id':f'SME-JA-{i+1:02}','borrower_name':f'Illustrative {categories[i%len(categories)]} company',
  'sector':categories[i%len(categories)],'reported_area':'Jebel Ali',
  'borrower_lat':str(lat+dr()),'borrower_lon':str(lon+dr()),
  'collateral_lat':str(lat+dr()+(0.022 if i%7==0 else 0)),'collateral_lon':str(lon+dr()+(0.020 if i%7==0 else 0)),
  'ead_aed':str(rng.choice([2250000,4800000,7600000,12000000,18800000,23000000,35000000])),
  'pd_pct':str(round(rng.uniform(1.25,4.2),2)), 'lgd_pct':str(rng.choice([25,30,35,40,45])),
  'insurance_status':rng.choice(['Unknown','Partial','Review needed']), 'data_class':'SYNTHETIC FINANCIAL EXPOSURE'})
 result=[]
 for x in rows:
  x=dict(x)
  for k in ['borrower_lat','borrower_lon','collateral_lat','collateral_lon','ead_aed','pd_pct','lgd_pct']:x[k]=float(x[k])
  result.append(x)
 return result

def match_point(lat,lon):
 hits=[]
 for s in SITES:
  m=haversine(lat,lon,s['lat'],s['lon'])
  if m<=s['radius_m']:hits.append({'site_id':s['id'],'distance_m':round(m),'radius_m':s['radius_m']})
 return sorted(hits,key=lambda h:h['distance_m'])

def summarize(pd_multiplier=2.0,lgd_uplift_pp=10.0,focus='jebelali'):
 if not 1<=pd_multiplier<=5 or not 0<=lgd_uplift_pp<=35:raise ValueError('Stress controls out of range')
 rows=[];loans=load_loans()
 for loan in loans:
  op_hits=match_point(loan['borrower_lat'],loan['borrower_lon'])
  col_hits=match_point(loan['collateral_lat'],loan['collateral_lon'])
  ops=bool(op_hits);coll=bool(col_hits)
  op_base=min(1,loan['pd_pct']/100);lg_base=min(1,loan['lgd_pct']/100)
  stressed_pd=min(1,op_base*pd_multiplier) if ops else op_base
  stressed_lgd=min(1,lg_base+lgd_uplift_pp/100) if coll else lg_base
  baseline=loan['ead_aed']*op_base*lg_base
  stressed=loan['ead_aed']*stressed_pd*stressed_lgd
  delta=max(0,stressed-baseline)
  relevance=int(any(x['site_id']==focus for x in op_hits+col_hits))
  nearest=min([x['distance_m'] for x in op_hits+col_hits] or [99999]); maxrad=max([x['radius_m'] for x in op_hits+col_hits] or [1])
  proximity=max(0,1-nearest/maxrad)
  # Important: INDEX of scenario geographic overlap; NOT a calibrated damage probability.
  score=round(min(100,24+45*proximity+18*int(ops and coll)+10*int(coll))) if ops or coll else 0
  reasons=[]
  if ops:reasons.append('Operating site near reported flood location')
  if coll:reasons.append('Collateral near reported flood location')
  if ops and coll:reasons.append('Two simultaneous exposure channels')
  if not (ops or coll):reasons.append('Outside named locality buffers')
  reasons.append('Location buffer is not measured inundation')
  rows.append({**loan,'ops':ops,'coll':coll,'op_hits':op_hits,'coll_hits':col_hits,'risk_index':score,
   'relevant_focus':relevance,'nearest_m':nearest if nearest!=99999 else None,'base_ecl':round(baseline),
   'stress_ecl':round(stressed),'delta_ecl':round(delta),'pd_stress_pct':round(stressed_pd*100,2),
   'lgd_stress_pct':round(stressed_lgd*100,2),'reasons':reasons,'exposure_channel': 'DUAL' if ops and coll else 'OPERATIONS' if ops else 'COLLATERAL' if coll else 'NONE'})
 rows.sort(key=lambda x:(x['relevant_focus'],x['delta_ecl']),reverse=True)
 return {'event':'APR 2024 UAE FLOODS','event_date':'2024-04-16','focus':focus,'sites':SITES,'method':METHOD,
   'assumptions':{'pd_multiplier':pd_multiplier,'lgd_uplift_pp':lgd_uplift_pp,'synthetic':True,'water_reenactment':'visualization only','depth_m':None,'accuracy':None},
   'summary':{'loans':len(rows),'total_ead':round(sum(x['ead_aed'] for x in rows)),
    'screened':sum(x['ops'] or x['coll'] for x in rows),'dual':sum(x['ops'] and x['coll'] for x in rows),
    'base':round(sum(x['base_ecl'] for x in rows)),'stress':round(sum(x['stress_ecl'] for x in rows)),
    'delta':round(sum(x['delta_ecl'] for x in rows)),'focus_loans':sum(x['relevant_focus'] for x in rows),
    'focus_delta':round(sum(x['delta_ecl'] for x in rows if x['relevant_focus']))},'loans':rows}

if __name__=='__main__':
 x=summarize();print(json.dumps(x['summary'],indent=2));print('Top',[(l['loan_id'],l['delta_ecl']) for l in x['loans'][:3]])
