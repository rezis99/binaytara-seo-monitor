"""
Binaytara SEO Monitor — Configuration
All constants, thresholds, and section definitions in one place.
"""

# ── GA4 ───────────────────────────────────────────────────────────
GA4_PROPERTY_ID = "468739074"

# ── GSC ───────────────────────────────────────────────────────────
GSC_SITE_URL = "sc-domain:binaytara.org"
SITE_DOMAIN = "https://binaytara.org"

# ── Section definitions (order matters; first match wins) ────
SECTIONS = [
    {"name": "TCN",         "prefix": "/cancernews"},
    {"name": "Journal",     "prefix": "/journal"},
    {"name": "Conferences", "prefix": "/projects/conferences"},
    {"name": "OncoBlast",   "prefix": "/projects/oncoblast"},
]
DEFAULT_SECTION = "Main Site"

# Consistent color per section (used across every chart)
SECTION_COLORS = {
    "TCN":         "#1B3A6B",
    "Journal":     "#2E8B57",
    "Conferences": "#C77C2E",
    "OncoBlast":   "#7E4E9B",
    "Main Site":   "#5F6B7A",
}

# ── Branded-term detection ────────────────────────────────────────
# A query counts as branded if it contains any of these (case-insensitive).
# Note: Ahrefs' entity detection uses "Binaytara Foundation"; we track the
# correct brand "Binaytara" but keep the phrase here only so branded queries
# that include it are still classified as branded (never shown as a label).
BRANDED_TERMS = [
    "binaytara",
    "binay tara",
    "the cancer news",
    "oncoblast",
    "ijccd",
    "binaytara foundation",
]

# ── Date defaults ─────────────────────────────────────────────────
DATA_LAG_DAYS = 3          # GA4/GSC processing lag
DEFAULT_PRESET = "Last 6 months"

DATE_PRESETS = {
    "Last 7 days":    7,
    "Last 28 days":   28,
    "Last 3 months":  90,
    "Last 6 months":  180,
    "Last 12 months": 365,
    "Custom":         None,
}

# Hero "monthly-scale" line: rolling total window (days)
ROLLING_WINDOW_DAYS = 28

# Granularity + smoothing options (global controls)
GRANULARITY_OPTIONS = ["Daily", "Weekly", "Monthly"]
SMOOTHING_OPTIONS = ["Raw", "7-day average", "28-day average"]

# ── Cache TTLs (seconds) ──────────────────────────────────────────
CACHE_TTL_MAIN = 3600      # 1 hour for GA4/GSC page-level and daily data
CACHE_TTL_QUERY = 1800     # 30 min for per-page / date-query data

# ── Opportunity thresholds ────────────────────────────────────────
CTR_OPP_MIN_IMPRESSIONS = 100
CTR_OPP_MAX_CTR = 0.02         # 2%

# Striking distance: agency standard is positions 11–20 (page 2).
# Configurable in the Opportunities tab; 8–20 is a common wider variant.
STRIKING_MIN_POSITION = 11
STRIKING_MAX_POSITION = 20
STRIKING_MIN_IMPRESSIONS = 50
STRIKING_BAND_PRESETS = {
    "11–20 (page 2, standard)": (11, 20),
    "8–20 (bottom of page 1 + page 2)": (8, 20),
    "5–20 (wide)": (5, 20),
    "4–15 (AI-era)": (4, 15),
}

DECLINE_MIN_CHANGE_PCT = -0.15  # −15%
DECLINE_MIN_PREV_USERS = 20
GROWTH_MIN_CHANGE_PCT = 0.25    # +25%
GROWTH_MIN_CURR_USERS = 30

# Position buckets (used on Search Performance + Keyword tabs)
POSITION_BUCKETS = [
    ("1–3 (Top 3)",   1, 3),
    ("4–10 (Page 1)", 4, 10),
    ("11–20 (Page 2)", 11, 20),
    ("21–50",         21, 50),
    ("51+",           51, 1000),
]

# ── API limits ────────────────────────────────────────────────────
GA4_ROW_LIMIT = 100_000
GSC_ROW_LIMIT = 25_000
GSC_QUERY_ROW_LIMIT = 25_000

# ── UI branding ───────────────────────────────────────────────────
BRAND_NAVY = "#1B3A6B"
BRAND_LIGHT_BLUE = "#E8F0FE"
BRAND_GREEN = "#1E7E34"
BRAND_RED = "#DC3545"
BRAND_GRAY = "#5F6B7A"
