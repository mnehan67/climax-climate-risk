# CLIMAX: 3-minute pitch (runs alongside ▶ PLAY STORY)

Numbers in [brackets] come from the screen after you run the real pipeline. Read them off the app; never memorise them in advance.

## 0:00–0:20 · Hook (story: alert card)
"On 16 April 2024 the UAE had the heaviest rain in 75 years of records. Everyone remembers the water.
Banks remember something else: weeks later, businesses that still couldn't open."

## 0:20–0:45 · The gap (CBUAE Challenge Profile 1, in its own words)
"The challenge asks how banks can see when a climate event *simultaneously damages the borrower's business and the pledged collateral*, and how to *shorten the detection time*." 


"The Central Bank's climate stress test models flood *damage* to property. Its own 2025 report says it
leaves out foregone revenue. That's the business that can't trade while water sits outside.
And a Zayed University study found 95% of Dubai's flooded area was still under water three days later.
Banks model how deep the water gets. Dubai's lesson is how long it stays."

## 0:45–1:00 · What we built (story: agent console streaming)
"CLIMAX is an agent that does what an analyst would need a week for. It searches the Sentinel-2 archive,
detects new water on every clear pass, measures how long it stayed around every building,
and joins that to the loan book. MBZUAI showed which streets flooded. We show which loans."

## 1:00–1:45 · Demo (story stages 1–5)
- Before: "Al Quoz, real satellite image, [N] real OpenStreetMap buildings."
- Storm: "This animation is the only thing that isn't measured. Everything after it is."
- Day 1: "[X] km² of new water, measured, not drawn."
- Days: "Watch the timeline. Buildings stay coloured while water is still around them. [N] buildings were wet for 7+ days."
- Loans: "Two losses. Duration drives default probability, because the business can't trade. Depth drives loss-given-default, because the collateral is damaged.
  [N] loans flagged, [N] hit on both. The loans are synthetic, but they sit on real buildings, assigned blind to the flood."

## 1:45–2:10 · The honesty moment (story stage 6: swipe)
"Could you just predict this from terrain? Left is a terrain model built before the storm. Right is what the satellite saw.
On a held-out half of the map it scores IoU [0.xx]. That's why we measure instead of guess."

## 2:10–2:35 · Ask it (story stage 7: Arabic question)
"Any analyst can ask, in Arabic or English. Every answer comes from tool calls you can audit, never from the model's imagination."

## 2:35–3:00 · Close (story stage 8 + open MEMO)
"One click gives the risk committee a memo with every scene ID, assumption and limitation.
For a 90-day pilot: swap synthetic loans for one bank's geocoded book, calibrate β on post-April-2024 arrears,
and add Sentinel-1 radar for cloudy days. CLIMAX turns a satellite pass into a review queue. People still make the decisions."

---

## How we score against the judging criteria (Playbook Exhibits 3–4)

| Criterion (Pioneers / Rising Stars) | What we show |
|---|---|
| Alignment & impact (15% / 25%) | Profile 1's exact problem: one event hits business and collateral together → DUAL channel. "Shorten detection time" → detected on **day 1–5** vs a quarterly review. Root causes R1–R3 → proposed asset-level hazard record (memo §8, audit file). |
| Effective use of government open data (15% / 20%) | **Dubai Land Department transactions (Data.Dubai)** price every pledged collateral from real AED/m² medians. Cite the file and its last-updated date on the slide. Plus Copernicus (EU), the EU Commission's JRC curves and OSM. |
| AI & emerging tech (15% / 20%) | A tool-calling agent (MBZUAI OpenEarthAgent pattern) in Arabic and English, satellite water detection, a CesiumJS 3D digital twin, and an honest forecast-vs-reality metric. |
| Feasibility & 90-day plan (20% / 15%) | Below. Runs on a laptop with free data, and the only new input is a bank's geocoded loan list. |
| Market potential (15%, Pioneers) | Below. |
| Communication (20%) | ▶ PLAY STORY, a 50-second guided demo. |

## 90-day pilot plan (with one bank + CBUAE sandbox)

| Weeks | Milestone | Done when |
|---|---|---|
| 1–2 | Data-sharing agreement; 1 bank SME book (≤ 2,000 loans) geocoded to building IDs / DLD plot numbers inside the bank's own environment | Geocoding match ≥ 90% |
| 3–4 | Replace synthetic loans; add Sentinel-1 radar for cloudy days; link the NCM rainfall record | Same April 2024 replay on real exposures |
| 5–8 | Calibrate β (PD uplift per day) on the bank's post-April-2024 arrears; calibrate the depth-damage curve on insurer claims | Back-test: flagged loans vs actual arrears (precision/recall reported) |
| 9–10 | Embed in the credit workflow: review queue + memo into the bank's monthly risk committee (root cause R4) | Risk committee uses it once |
| 11–12 | CBUAE supervisory view: aggregated, anonymised exposure by district; propose the asset-hazard record as a reporting template | CBUAE feedback session; go/no-go for 3 banks |

## Business model
- **Banks / Islamic banks**: annual SaaS licence per portfolio (on-premise option for data privacy), plus an event-triggered re-run within 24 h of any NCM red alert.
- **Insurers / Takaful**: claims-triage and accumulation view (same engine; collateral = insured asset).
- **CBUAE**: a supervisory dashboard and the open asset-hazard data standard. Adoption drives bank demand.
- **Costs stay low**: Sentinel-2, Copernicus DEM and OSM are free; DLD is open data; compute is a laptop or one VM.

## Q&A cards

- **Is the data real?** Water, persistence and buildings are real (Sentinel-2, OSM). Depth is an indicative DEM estimate. The loans are synthetic, and the badge says so on screen.
- **How accurate is the water detection?** MNDWI is the standard index (Xu 2006). We don't claim a pixel accuracy without ground truth. We show the cloud-free share of every pass and the forecast IoU on a spatial holdout.
- **Why a 15 m ring?** A satellite can't see water under a roof. It sees the street and yard around the building.
- **Why β = 0.10/day?** It's an explicit assumption: 10 days of interruption doubles PD. It's a slider, and the pilot calibrates it on arrears.
- **Clouds?** Optical can't see through them. That's why persistence is a lower bound. Next step is Sentinel-1 SAR (EarthDial-style multi-sensor).
- **Why not a big vision-language model?** We follow MBZUAI's OpenEarthAgent pattern: a planner calling verifiable tools. Every number is traceable, and it runs on a laptop.
- **Where is the government data?** Dubai Land Department transactions from Data.Dubai give collateral AED/m² per district (the memo shows the rows used and the medians). The 90-day pilot adds NCM rainfall and Dubai Municipality drainage.
- **Why CesiumJS?** It's a 3D digital twin judges can fly through: Bing aerial + OSM buildings from Cesium ion, with our measured layers on top. If the venue internet drops, press "3D" to switch to the offline renderer. Same data, same demo.
- **What about heat or coastal surge?** Out of scope for 24 h. The same building-level join works with any hazard layer.
- **Who pays?** Banks, for portfolio triage and ICAAP climate sections. CBUAE, for supervisory concentration views. Insurers, for claims triage.

## Pre-flight (10 minutes before)
1. The badge says **REAL** (not TEST), and the "COLLATERAL AED/m²" chip says **DLD · DATA.DUBAI**.
1b. The top-right button says **3D · CESIUM** and aerial imagery is visible. If not (no internet), click it to switch to LITE.
2. Run PLAY STORY once, all the way through.
3. Test the ask bar with one English and one Arabic question.
4. MEMO opens.
5. Wi-Fi OFF test: the app still works.
6. Keep a screen recording of a full story run as backup.
