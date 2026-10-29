"""
Binaytara SEO Monitor — GSC Data Fetcher
All Google Search Console Search Analytics API calls with Streamlit caching.

Freshness note: no dataState is set, so the API returns finalized ("full")
data only. That automatically drops the most recent ~2–3 partial days, which
is why the daily lines never show an artificial end-of-range dip.
"""

import streamlit as st
import pandas as pd
from auth import gsc_service
from config import (
    GSC_SITE_URL, GSC_ROW_LIMIT, GSC_QUERY_ROW_LIMIT,
    CACHE_TTL_MAIN, CACHE_TTL_QUERY,
)


def _query(body: dict) -> list:
    """Execute a GSC searchAnalytics.query and return rows."""
    svc = gsc_service()
    resp = svc.searchanalytics().query(siteUrl=GSC_SITE_URL, body=body).execute()
    return resp.get("rows", [])


def _paginate(dimensions, start, end, row_limit, extra=None) -> list:
    """Run a paginated searchAnalytics query across all rows."""
    all_rows = []
    start_row = 0
    while True:
        body = {
            "startDate": start, "endDate": end,
            "dimensions": dimensions,
            "rowLimit": row_limit, "startRow": start_row,
        }
        if extra:
            body.update(extra)
        rows = _query(body)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < row_limit:
            break
        start_row += row_limit
    return all_rows


# ── Daily site totals (cheap: <= range length rows) ───────────────

@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_gsc_daily_totals(start, end) -> pd.DataFrame:
    """Daily site-wide GSC totals. Columns: date, clicks, impressions, ctr, position."""
    rows = _paginate(["date"], start, end, GSC_ROW_LIMIT)
    if not rows:
        return pd.DataFrame(columns=["date", "clicks", "impressions", "ctr", "position"])
    df = pd.DataFrame([{
        "date": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"],
        "ctr": r["ctr"], "position": r["position"],
    } for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


# ── Page-level summary ────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_gsc_page_summary(start, end) -> pd.DataFrame:
    """Page-level GSC data (raw URLs). Columns: page, gsc_clicks, gsc_impressions, gsc_ctr, gsc_position."""
    rows = _paginate(["page"], start, end, GSC_ROW_LIMIT)
    if not rows:
        return pd.DataFrame(columns=["page", "gsc_clicks", "gsc_impressions", "gsc_ctr", "gsc_position"])
    df = pd.DataFrame([{
        "page": r["keys"][0], "gsc_clicks": r["clicks"], "gsc_impressions": r["impressions"],
        "gsc_ctr": r["ctr"], "gsc_position": r["position"],
    } for r in rows])
    df = df[df["page"].str.contains("binaytara.org", na=False)].copy()
    return df


# ── Query-level totals for a period (snapshot) ────────────────────

@st.cache_data(ttl=CACHE_TTL_QUERY, show_spinner=False)
def fetch_gsc_query_totals(start, end) -> pd.DataFrame:
    """Site-wide query totals for one period. Columns: query, clicks, impressions, ctr, position."""
    rows = _paginate(["query"], start, end, GSC_QUERY_ROW_LIMIT)
    if not rows:
        return pd.DataFrame(columns=["query", "clicks", "impressions", "ctr", "position"])
    df = pd.DataFrame([{
        "query": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"],
        "ctr": r["ctr"], "position": r["position"],
    } for r in rows])
    return df


# ── Device split ──────────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_gsc_device_totals(start, end) -> pd.DataFrame:
    """Clicks/impressions by device for a period. Columns: device, clicks, impressions, ctr, position."""
    rows = _paginate(["device"], start, end, 100)
    if not rows:
        return pd.DataFrame(columns=["device", "clicks", "impressions", "ctr", "position"])
    df = pd.DataFrame([{
        "device": r["keys"][0].title(), "clicks": r["clicks"], "impressions": r["impressions"],
        "ctr": r["ctr"], "position": r["position"],
    } for r in rows])
    return df


# ── Date x query (heavier; powers optional bucket/brand trends) ───

@st.cache_data(ttl=CACHE_TTL_QUERY, show_spinner=False)
def fetch_gsc_date_query(start, end) -> pd.DataFrame:
    """
    Daily query-level rows. Columns: date, query, clicks, impressions, ctr, position.
    Heavier call (one row per query per day); used only when the position-bucket
    trend is explicitly loaded on the Search Performance tab.
    """
    rows = _paginate(["date", "query"], start, end, GSC_QUERY_ROW_LIMIT)
    if not rows:
        return pd.DataFrame(columns=["date", "query", "clicks", "impressions", "ctr", "position"])
    df = pd.DataFrame([{
        "date": r["keys"][0], "query": r["keys"][1], "clicks": r["clicks"],
        "impressions": r["impressions"], "ctr": r["ctr"], "position": r["position"],
    } for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


# ── Query-level data for a single page ────────────────────────────

@st.cache_data(ttl=CACHE_TTL_QUERY, show_spinner=False)
def fetch_gsc_queries_for_page(page_url, start, end) -> pd.DataFrame:
    """Query-level GSC data for one page. Columns: query, clicks, impressions, ctr, position."""
    extra = {"dimensionFilterGroups": [{
        "filters": [{"dimension": "page", "expression": page_url, "operator": "equals"}]
    }]}
    rows = _paginate(["page", "query"], start, end, GSC_QUERY_ROW_LIMIT, extra=extra)
    if not rows:
        return pd.DataFrame(columns=["query", "clicks", "impressions", "ctr", "position"])
    return pd.DataFrame([{
        "query": r["keys"][1], "clicks": r["clicks"], "impressions": r["impressions"],
        "ctr": r["ctr"], "position": round(r["position"], 1),
    } for r in rows])


# ── Compare queries between two periods (New/Lost/Retained) ────────

def compare_queries(page_url, curr_start, curr_end, prev_start, prev_end) -> pd.DataFrame:
    """Fetch queries for both periods and compute New/Lost/Retained diffs."""
    curr_df = fetch_gsc_queries_for_page(page_url, curr_start, curr_end)
    prev_df = fetch_gsc_queries_for_page(page_url, prev_start, prev_end)

    curr_map = {r["query"]: r.to_dict() for _, r in curr_df.iterrows()} if not curr_df.empty else {}
    prev_map = {r["query"]: r.to_dict() for _, r in prev_df.iterrows()} if not prev_df.empty else {}

    all_queries = set(curr_map) | set(prev_map)
    if not all_queries:
        return pd.DataFrame()

    result = []
    for q in all_queries:
        c, p = curr_map.get(q), prev_map.get(q)
        status = "New" if p is None else ("Lost" if c is None else "Retained")
        c_clicks, p_clicks = (c["clicks"] if c else 0), (p["clicks"] if p else 0)
        c_impr, p_impr = (c["impressions"] if c else 0), (p["impressions"] if p else 0)
        c_ctr, p_ctr = (c["ctr"] if c else 0), (p["ctr"] if p else 0)
        c_pos, p_pos = (c["position"] if c else None), (p["position"] if p else None)
        pos_delta = round(c_pos - p_pos, 1) if (c_pos is not None and p_pos is not None) else None
        result.append({
            "query": q, "status": status,
            "clicks_current": c_clicks, "clicks_previous": p_clicks, "clicks_change": c_clicks - p_clicks,
            "impressions_current": c_impr, "impressions_previous": p_impr, "impressions_change": c_impr - p_impr,
            "ctr_current": c_ctr, "ctr_previous": p_ctr,
            "position_current": c_pos, "position_previous": p_pos, "position_change": pos_delta,
        })

    df = pd.DataFrame(result)
    status_order = {"Lost": 0, "Retained": 1, "New": 2}
    df["_s"] = df["status"].map(status_order)
    df = df.sort_values(["_s", "clicks_change"], ascending=[True, True]).drop(columns=["_s"])
    return df.reset_index(drop=True)
