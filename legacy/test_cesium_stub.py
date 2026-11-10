"""Tests only 3D code-path wiring via a Cesium-compatible stub, not real remote tiles."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import sys,json,re
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import summarize
ROOT=Path(__file__).resolve().parents[1]
FAKE_JS=r'''window.__tiles=0;window.__flights=0;
const CLR=()=>({withAlpha:()=>CLR()});
class Viewer {constructor(){this.scene={globe:{ellipsoid:{}},fog:{},postProcessStages:{fxaa:{}},screenSpaceCameraController:{},canvas:document.createElement('canvas'),primitives:{add:()=>{}},pick:()=>null};this.camera={setView:()=>{window.__flights++},flyTo:()=>{window.__flights++}};this.entities={add:o=>o,remove:()=>{}};this.cesiumWidget={};}destroy(){}}
window.Cesium={Ion:{defaultAccessToken:''},Viewer,UrlTemplateImageryProvider:class{},ImageryLayer:class{},EllipsoidTerrainProvider:class{},Cartesian3:{fromDegrees:(...x)=>x,fromDegreesArray:x=>x},Cartesian2:class{},DistanceDisplayCondition:class{},Math:{toRadians:x=>x*Math.PI/180},ScreenSpaceEventHandler:class{setInputAction(){}},ScreenSpaceEventType:{LEFT_CLICK:0},Color:{fromCssColorString:CLR},createOsmBuildingsAsync:async()=>({tileVisible:{addEventListener:cb=>{window.__tiles++;setTimeout(cb,25)}}})};'''
F='''<script>window.fetch=async function(u){return new Response(JSON.stringify(String(u).includes('/api/config')?{cesiumToken:'RENDERER_STUB_TOKEN'}:%s),{status:200,headers:{'content-type':'application/json'}})}</script>'''%json.dumps(summarize(),separators=(',',':'))
h=(ROOT/'index.html').read_text()
h=re.sub(r'<link rel="preconnect"[^>]+>','',h);h=re.sub(r'<link href="https://fonts.googleapis.com[^>]+>','',h)
h=h.replace('<link href="assets/style.css" rel="stylesheet">','<style>'+(ROOT/'assets/style.css').read_text()+'</style>')
h=h.replace('<script src="assets/app.js" defer></script>',F+'<script>'+FAKE_JS+'</script><script>'+(ROOT/'assets/app.js').read_text()+'</script>')
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':1600,'height':900})
 errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
 page.set_content(h,wait_until='domcontentloaded');page.wait_for_timeout(300)
 print('3D status:',page.locator('#sceneStatus').inner_text());assert page.evaluate('window.__tiles')==1
 assert page.locator('#sceneStatus').inner_text()=='OSM BUILDINGS LIVE'
 page.locator('.site[data-site="alquoz"]').click();page.wait_for_timeout(150)
 assert page.evaluate('window.__flights')>=2
 page.locator('.time-dot[data-step="storm"]').click();page.wait_for_timeout(200)
 page.locator('.time-dot[data-step="impact"]').click();page.wait_for_timeout(120)
 assert not errs,errs
 print('PASS: Cesium init, building callback, camera changes, entity updates (stub ONLY)')
 browser.close()
