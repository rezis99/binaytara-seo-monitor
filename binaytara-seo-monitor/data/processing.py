"""
Binaytara SEO Monitor — Data Processing
Path normalization, section classification, branded detection,
GA4<->GSC joining (deduplicated), and time-series resampling.
"""

from urllib.parse import unquote
import re
import pandas as pd
from config import (
    SECTIONS, DEFAULT_SECTION, SITE_DOMAIN, BRANDED_TERMS,
    POSITION_BUCKETS,
)


# ── Path helpers ──────────────────────────────────────────────────

def normalize_path(raw: str) -> str:
    """
    Normalize a GA4 pagePath or a full URL into a clean path.
    Strips domain, query params, fragments, trailing slash; decodes; lowercases.
    Lowercasing guarantees GA4<->GSC and variant URLs collapse to one key.
    """
    p = str(raw).strip()
    if p.startswith("http"):
        # remove scheme + host, keep the path onward
        rest = p.split("//", 1)[-1]
        p = "/" + rest.split("/", 1)[1] if "/" in rest else "/"
    for prefix in [SITE_DOMAIN, "https://binaytara.org", "http://binaytara.org", "binaytara.org"]:
        if p.startswith(prefix):
            p = p[len(prefix):]
    p = p.split("?")[0].split("#")[0]      # strip query & fragment
    p = p.rstrip("/")                       # strip trailing slash
    try:
        p = unquote(p)
    except Exception:
        pass
    p = p.lower()
    if not p:
        p = "/"
    return p


def classify_section(path: str) -> str:
    """Assign a page path to one of the five site sections."""
    path = normalize_path(path)
    for sec in SECTIONS:
        prefix = sec["prefix"]
        if path == prefix or path.startswith(prefix + "/"):
            return sec["name"]
    return DEFAULT_SECTION


def strip_domain(url: str) -> str:
    """Convert a full GSC URL to a GA4-style normalized path."""
    return normalize_path(url)


# ── Branded detection ─────────────────────────────────────────────

_BRANDED_RE = re.compile(
    "|".join(re.escape(t) for t in BRANDED_TERMS), flags=re.IGNORECASE
)


def is_branded(query: str) -> bool:
    """True if the query contains any branded term."""
    if not isinstance(query, str):
        return False
    return bool(_BRANDED_RE.search(query))


def branded_label(query: str) -> str:
    return "Branded" if is_branded(query) else "Non-branded"


# ── Position bucketing ────────────────────────────────────────────

def position_bucket(pos) -> str:
    """Map an average position to a human bucket label."""
    if pos is None or pd.isna(pos):
        return "Unranked"
    for label, lo, hi in POSITION_BUCKETS:
        if lo <= pos <= hi:
            return label
    return "51+"


def bucket_order() -> list:
    return [label for label, _, _ in POSITION_BUCKETS]


# ── GSC page-summary dedupe (THE duplicate-row fix) ───────────────

def aggregate_gsc_by_path(gsc_df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse GSC page rows to ONE row per normalized path.

    Why this exists: GSC can return several URL variants that normalize to the
    same path (http/https, trailing slash, case, encoded characters). If those
    are left in place, a left join against one GA4 page row multiplies into
    several identical-looking rows — which is what produced the same page
    appearing 3–4 times in the gainers/losers lists in v1.

    Clicks/impressions are summed; CTR and position are recomputed as
    impression-weighted values so the collapsed row stays accurate.
    """
    cols = ["page", "gsc_clicks", "gsc_impressions", "gsc_ctr", "gsc_position"]
    if gsc_df is None or gsc_df.empty:
        return pd.DataFrame(columns=["_join_path", *cols[1:]])

    df = gsc_df.copy()
    df["_join_path"] = df["page"].apply(strip_domain)
    df["gsc_clicks"] = pd.to_numeric(df["gsc_clicks"], errors="coerce").fillna(0)
    df["gsc_impressions"] = pd.to_numeric(df["gsc_impressions"], errors="coerce").fillna(0)
    df["gsc_position"] = pd.to_numeric(df["gsc_position"], errors="coerce")
    df["_pos_weight"] = df["gsc_position"] * df["gsc_impressions"]

    agg = df.groupby("_join_path", as_index=False).agg(
        gsc_clicks=("gsc_clicks", "sum"),
        gsc_impressions=("gsc_impressions", "sum"),
        _pos_weight=("_pos_weight", "sum"),
    )
    agg["gsc_ctr"] = agg.apply(
        lambda r: (r["gsc_clicks"] / r["gsc_impressions"]) if r["gsc_impressions"] > 0 else 0.0,
        axis=1,
    )
    agg["gsc_position"] = agg.apply(
        lambda r: (r["_pos_weight"] / r["gsc_impressions"]) if r["gsc_impressions"] > 0 else None,
        axis=1,
    )
    agg.drop(columns=["_pos_weight"], inplace=True)
    return agg


# ── Joining ───────────────────────────────────────────────────────

def join_ga4_gsc(ga4_df: pd.DataFrame, gsc_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join GA4 page data with GSC page data on normalized path.
    GA4 is the left side so every GA4 page appears even without GSC data.
    The GSC side is deduplicated first (see aggregate_gsc_by_path) so the
    join is strictly one-to-one and never multiplies rows.
    """
    if ga4_df is None or ga4_df.empty:
        return ga4_df

    ga4_df = ga4_df.copy()
    ga4_df["_join_path"] = ga4_df["page_path"].apply(normalize_path)
    # Guard: never let the GA4 side carry duplicate paths into the join either.
    if ga4_df["_join_path"].duplicated().any():
        num_cols = [c for c in ga4_df.columns if ga4_df[c].dtype.kind in "if" and c != "_join_path"]
        first_cols = [c for c in ga4_df.columns if c not in num_cols and c != "_join_path"]
        agg_spec = {c: "sum" for c in num_cols}
        agg_spec.update({c: "first" for c in first_cols})
        ga4_df = ga4_df.groupby("_join_path", as_index=False).agg(agg_spec)

    gsc_agg = aggregate_gsc_by_path(gsc_df)
    if gsc_agg.empty:
        for col in ["gsc_clicks", "gsc_impressions", "gsc_ctr", "gsc_position"]:
            ga4_df[col] = None
        ga4_df.drop(columns=["_join_path"], inplace=True, errors="ignore")
        return ga4_df

    merged = ga4_df.merge(gsc_agg, on="_join_path", how="left")
    merged.drop(columns=["_join_path"], inplace=True, errors="ignore")
    return merged


# ── Comparison helpers ────────────────────────────────────────────

def compute_change(current: float, previous: float):
    """Return (absolute_change, pct_change). Handles zeros safely."""
    delta = (current or 0) - (previous or 0)
    pct = (delta / previous) if previous else None
    return delta, pct


def signal_label(current: float, previous: float) -> str:
    """Assign a traffic signal label to a page."""
    if current > 0 and previous == 0:
        return "🆕 New"
    if current == 0 and previous == 0:
        return "—"
    if previous > 0 and current > previous:
        return "✓ Growing"
    if previous > 0 and current < previous * 0.85:
        return "📉 Declining"
    return "→ Stable"


# ── Time-series resampling (granularity + smoothing) ──────────────

_FREQ_MAP = {"Daily": "D", "Weekly": "W-MON", "Monthly": "MS"}


def resample_timeseries(df: pd.DataFrame, date_col: str, freq_label: str,
                        sum_cols: list, weighted_mean_cols: list = None,
                        weight_col: str = "impressions") -> pd.DataFrame:
    """
    Resample a daily time series to Daily/Weekly/Monthly.
    sum_cols are summed; weighted_mean_cols are impression-weighted averages
    (correct for CTR and average position, which must never be plain-averaged).
    """
    if df is None or df.empty:
        return df
    freq = _FREQ_MAP.get(freq_label, "D")
    weighted_mean_cols = weighted_mean_cols or []

    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col])
    d = d.set_index(date_col).sort_index()

    out = pd.DataFrame()
    if sum_cols:
        out = d[sum_cols].resample(freq).sum()

    for col in weighted_mean_cols:
        if col in d.columns and weight_col in d.columns:
            num = (d[col] * d[weight_col]).resample(freq).sum()
            den = d[weight_col].resample(freq).sum()
            out[col] = num / den.replace(0, pd.NA)

    out = out.reset_index()
    return out


def rolling_total(series: pd.Series, window: int) -> pd.Series:
    """Rolling sum over `window` rows; only full windows (min_periods=window)."""
    return series.rolling(window=window, min_periods=window).sum()


def moving_average(series: pd.Series, window: int) -> pd.Series:
    """Trailing moving average; partial windows allowed so the line starts early."""
    return series.rolling(window=window, min_periods=1).mean()


def apply_smoothing(series: pd.Series, smoothing_label: str) -> pd.Series:
    if smoothing_label == "7-day average":
        return moving_average(series, 7)
    if smoothing_label == "28-day average":
        return moving_average(series, 28)
    return series
