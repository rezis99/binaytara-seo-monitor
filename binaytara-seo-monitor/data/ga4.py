"""
Binaytara SEO Monitor — GA4 Data Fetcher
All GA4 Data API calls with Streamlit caching.
"""

import streamlit as st
import pandas as pd
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Dimension, Metric,
    FilterExpression, Filter,
)
from auth import ga4_client
from config import GA4_PROPERTY_ID, GA4_ROW_LIMIT, CACHE_TTL_MAIN
from data.processing import normalize_path, classify_section


def _property() -> str:
    return f"properties/{GA4_PROPERTY_ID}"


def _organic_filter() -> FilterExpression:
    return FilterExpression(
        filter=Filter(
            field_name="sessionDefaultChannelGroup",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value="Organic Search",
            ),
        )
    )


def _run_report(dims, mets, start, end, dim_filter=None,
                limit=GA4_ROW_LIMIT, offset=0):
    """Generic GA4 report runner with pagination. Returns list[dict]."""
    client = ga4_client()
    all_rows = []
    current_offset = offset
    while True:
        request = RunReportRequest(
            property=_property(),
            date_ranges=[DateRange(start_date=start, end_date=end)],
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in mets],
            limit=limit,
            offset=current_offset,
        )
        if dim_filter:
            request.dimension_filter = dim_filter
        response = client.run_report(request)
        for row in response.rows:
            d = {}
            for i, dim in enumerate(dims):
                d[dim] = row.dimension_values[i].value
            for i, met in enumerate(mets):
                val = row.metric_values[i].value
                try:
                    d[met] = int(val) if "." not in val else float(val)
                except (ValueError, TypeError):
                    d[met] = val
            all_rows.append(d)
        if len(response.rows) < limit:
            break
        current_offset += limit
    return all_rows


# ── Daily site traffic ────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_daily_traffic(start, end, organic_only=True) -> pd.DataFrame:
    """Daily users and sessions for the whole site. Columns: date, totalUsers, sessions, newUsers, screenPageViews."""
    dim_filter = _organic_filter() if organic_only else None
    rows = _run_report(["date"], ["totalUsers", "sessions", "newUsers", "screenPageViews"],
                       start, end, dim_filter)
    cols = ["date", "totalUsers", "sessions", "newUsers", "screenPageViews"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    for c in ["totalUsers", "sessions", "newUsers", "screenPageViews"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    return df.sort_values("date").reset_index(drop=True)


# ── Page-level traffic ────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_page_traffic(start, end, organic_only=True) -> pd.DataFrame:
    """Page-level aggregated traffic. One row per normalized path."""
    dim_filter = _organic_filter() if organic_only else None
    rows = _run_report(["pagePath"],
                       ["totalUsers", "sessions", "newUsers", "engagementRate", "averageSessionDuration"],
                       start, end, dim_filter)
    cols = ["page_path", "section", "totalUsers", "sessions", "newUsers", "engagementRate", "avgSessionDuration"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    df.rename(columns={"pagePath": "page_path", "averageSessionDuration": "avgSessionDuration"}, inplace=True)
    df["page_path"] = df["page_path"].apply(normalize_path)
    df = df[df["page_path"] != "(not set)"].copy()
    for c in ["totalUsers", "sessions", "newUsers"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["engagementRate"] = pd.to_numeric(df["engagementRate"], errors="coerce").fillna(0)
    df["avgSessionDuration"] = pd.to_numeric(df["avgSessionDuration"], errors="coerce").fillna(0)
    df = df.groupby("page_path", as_index=False).agg({
        "totalUsers": "sum", "sessions": "sum", "newUsers": "sum",
        "engagementRate": "mean", "avgSessionDuration": "mean",
    })
    df["section"] = df["page_path"].apply(classify_section)
    return df.sort_values("totalUsers", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_daily_by_page(start, end, organic_only=True) -> pd.DataFrame:
    """Daily users by page path (for section-over-time). Columns: page_path, date, section, totalUsers."""
    dim_filter = _organic_filter() if organic_only else None
    rows = _run_report(["pagePath", "date"], ["totalUsers"], start, end, dim_filter)
    if not rows:
        return pd.DataFrame(columns=["page_path", "date", "section", "totalUsers"])
    df = pd.DataFrame(rows)
    df.rename(columns={"pagePath": "page_path"}, inplace=True)
    df["page_path"] = df["page_path"].apply(normalize_path)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df["totalUsers"] = pd.to_numeric(df["totalUsers"], errors="coerce").fillna(0).astype(int)
    df["section"] = df["page_path"].apply(classify_section)
    return df


@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_daily_by_section(start, end, organic_only=True) -> pd.DataFrame:
    """Daily users aggregated to section. Columns: date, section, totalUsers."""
    by_page = fetch_daily_by_page(start, end, organic_only)
    if by_page.empty:
        return pd.DataFrame(columns=["date", "section", "totalUsers"])
    return (by_page.groupby(["date", "section"], as_index=False)["totalUsers"].sum()
            .sort_values("date").reset_index(drop=True))


# ── Channel + geography ───────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_channel_traffic(start, end) -> pd.DataFrame:
    """Traffic by channel group (no organic filter). Columns: channel, totalUsers, sessions."""
    rows = _run_report(["sessionDefaultChannelGroup"], ["totalUsers", "sessions"], start, end)
    if not rows:
        return pd.DataFrame(columns=["channel", "totalUsers", "sessions"])
    df = pd.DataFrame(rows)
    df.rename(columns={"sessionDefaultChannelGroup": "channel"}, inplace=True)
    for c in ["totalUsers", "sessions"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    return df


@st.cache_data(ttl=CACHE_TTL_MAIN, show_spinner=False)
def fetch_country_traffic(start, end, organic_only=True) -> pd.DataFrame:
    """Traffic by country. Columns: country, totalUsers, sessions."""
    dim_filter = _organic_filter() if organic_only else None
    rows = _run_report(["country"], ["totalUsers", "sessions"], start, end, dim_filter)
    if not rows:
        return pd.DataFrame(columns=["country", "totalUsers", "sessions"])
    df = pd.DataFrame(rows)
    for c in ["totalUsers", "sessions"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df = df[df["country"] != "(not set)"].copy()
    return df.sort_values("totalUsers", ascending=False).reset_index(drop=True)
