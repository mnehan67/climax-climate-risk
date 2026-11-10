"""Screenshot/browser interaction suite in an environment with browser network navigation blocked.
Runs the exact app HTML/CSS/JS in about:blank, intercepts only the backend fetch calls.
Full HTTP server and calculations are separately tested in test_engine.py.
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import sys, json,base64,re
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import summarize
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'index.html').read_text()
css=(ROOT/'assets/style.css').read_text()
js=(ROOT/'assets/app.js').read_text()
base=summarize()
triple=summarize(3,10)
pd_cases=json.dumps({'base':base,'triple':triple},separators=(',',':'))
fetch_mock=f'''<script>const _fixtures={pd_cases};window.fetch=async function(url){{const s=String(url),u=new URL(s,'https://test.invalid');let v={{}};if(u.pathname==='/api/config')v={{cesiumToken:'',gpuModelLoaded:false}};else if(u.pathname==='/api/case')v=_fixtures.base;else if(u.pathname==='/api/stress')v=Number(u.searchParams.get('pd'))>=2.75?_fixtures.triple:_fixtures.base;return new Response(JSON.stringify(v),{{status:200,headers:{{'content-type':'application/json'}}}})}};</script>'''
html=re.sub(r'<link rel="preconnect"[^>]+>','',html)
html=html.replace('<head>','<head><base href="https://climax.test/">',1)
html=re.sub(r'<link href="https://fonts.googleapis.com[^>]+>','',html)
html=html.replace('<link href="assets/style.css" rel="stylesheet">','<style>'+css+'</style>')
# No network resources; exact app JS runs unmodified except replacing source image paths with data URIs.
html=html.replace('<script src="assets/app.js" defer></script>',fetch_mock+'<script>'+js+'</script>')
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':1600,'height':900},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('https://climax.test/assets/**', lambda route: route.fulfill(path=str(ROOT / 'assets' / route.request.url.split('/assets/',1)[1])))
 page.set_content(html,wait_until='domcontentloaded',timeout=40000)
 page.wait_for_timeout(1100)
 page.screenshot(path=str(ROOT/'tests'/'01_ready.png'))
 print('ready:',page.locator('#sceneStatus').inner_text(),page.locator('#readyLocation').inner_text())
 page.locator('.time-dot[data-step="storm"]').click()
 page.wait_for_timeout(550)
 page.screenshot(path=str(ROOT/'tests'/'02_storm.png'))
 print('storm:',page.locator('#panelStorm').is_visible())
 page.locator('.time-dot[data-step="evidence"]').click()
 page.wait_for_timeout(250)
 page.locator('.sat-tab[data-sat="mask"]').click()
 assert page.locator('.sat-pic > img').first.evaluate('(x)=>x.complete && x.naturalWidth>0'), 'satellite image not loaded'
 page.screenshot(path=str(ROOT/'tests'/'03_evidence.png'))
 print('evidence:',page.locator('#satNote').inner_text())
 page.locator('.time-dot[data-step="impact"]').click()
 page.wait_for_timeout(250)
 page.screenshot(path=str(ROOT/'tests'/'04_impact.png'))
 before=page.locator('#focusDelta').inner_text()
 page.locator('#pdRange').fill('3')
 page.wait_for_timeout(400)
 after=page.locator('#focusDelta').inner_text()
 print('impact:',page.locator('#screenCount').inner_text(),before,'→',after)
 assert before!=after
 page.locator('#detailsBtn').click()
 print('drawer:',page.locator('#drawer').is_visible())
 page.locator('#drawerClose').click()
 assert page.locator('#drawer').is_hidden()
 page.locator('#resetBtn').click()
 assert page.locator('#panelReady').is_visible()
 page.locator('#runBtn').click()
 page.wait_for_timeout(16600)
 assert page.locator('#panelImpact').is_visible(), 'one-button RUN did not complete'
 assert page.locator('#runLabel').inner_text()=='REPLAY EVENT'
 print('full replay:',page.locator('#panelImpact').is_visible())
 print('errors:',errors)
 assert not errors,errors
 mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
 mobile.route('https://climax.test/assets/**', lambda route: route.fulfill(path=str(ROOT / 'assets' / route.request.url.split('/assets/',1)[1])))
 mobile.set_content(html,wait_until='domcontentloaded',timeout=40000)
 mobile.wait_for_timeout(350)
 mobile.screenshot(path=str(ROOT/'tests'/'05_mobile.png'))
 print('mobile:',mobile.locator('#runBtn').is_visible())
 browser.close()
