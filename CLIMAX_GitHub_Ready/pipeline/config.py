"""Central configuration for the CLIMAX earth-observation pipeline.

Everything here is a documented, editable assumption. Nothing is hidden in code.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "generated"

EVENT_DATE = "2024-04-16"          # storm day (UAE, 16 April 2024)
PRE_WINDOW = ("2024-03-20", "2024-04-15")   # search for the clearest pre-storm scene
POST_WINDOW = ("2024-04-16", "2024-05-25")  # every usable post-storm scene -> persistence

# Areas of interest: (lon_min, lat_min, lon_max, lat_max). ~6 x 6 km each => ~600 x 600 px at 10 m.
AOIS = {
    "alquoz": {
        "name": "Al Quoz & Al Barsha", "short": "AL QUOZ",
        "bbox": (55.200, 25.110, 55.262, 25.166),
        "why": "Industrial/warehouse district; reported long-standing water on First Al Khail St (The National).",
    },
    "jebelali": {
        "name": "Al Furjan · Discovery Gardens · Jebel Ali", "short": "JEBEL ALI",
        "bbox": (55.110, 25.005, 55.172, 25.061),
        "why": "Residential + light-industrial; waterlogged routes reported days after the storm; visible in ESA's 17 Apr Sentinel-2 image.",
    },
    "dxb": {
        "name": "DXB Airport · Garhoud · Rashidiya", "short": "DXB",
        "bbox": (55.330, 25.222, 55.392, 25.278),
        "why": "Airport operations disrupted (2,155 cancellations, Dubai Airports); dense logistics exposure.",
    },
}

RES_M = 10                     # analysis grid (m), UTM zone 40N
UTM_EPSG = 32640

# --- Sentinel-2 L2A via Element 84 Earth Search (public COGs, no key) -------------
STAC_URL = "https://earth-search.aws.element84.com/v1"
S2_COLLECTION = "sentinel-2-l2a"
MAX_SCENE_CLOUD = 80           # scene-level filter; pixel-level cloud masking does the real work
MIN_AOI_VALID = 0.55           # a date is used only if >= 55% of AOI pixels are cloud-free
# SCL classes treated as invalid: 0 nodata, 1 saturated, 8/9 cloud, 10 cirrus.
# NOTE: class 3 (cloud shadow) is NOT masked because dark floodwater is often mislabelled as shadow.
SCL_INVALID = (0, 1, 8, 9, 10)

# Water index: MNDWI = (Green - SWIR1)/(Green + SWIR1)  (Xu 2006). Threshold by Otsu, clamped.
MNDWI_CLAMP = (0.0, 0.30)
MIN_FLOOD_PATCH_PX = 6         # remove speckle smaller than ~600 m^2

# --- Copernicus DEM GLO-30 (public COG on AWS) -------------------------------------
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_N25_00_E055_00_DEM/Copernicus_DSM_COG_10_N25_00_E055_00_DEM.tif")
DEPTH_CAP_M = 2.5              # FwDET-style depth estimates are capped (coarse DSM, +-0.5 m or worse)

# --- OpenStreetMap buildings via Overpass ------------------------------------------
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
BUILDING_RING_M = 15           # water is measured in a 15 m ring AROUND each footprint (roofs never look wet)

# --- Synthetic loan book (clearly labelled) -------------------------------------
N_LOANS = 140
LOAN_SEED = 20240416
