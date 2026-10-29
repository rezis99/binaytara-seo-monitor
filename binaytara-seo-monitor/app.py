"""
Binaytara SEO Monitor — Main Application
Interactive GA4 + GSC organic-traffic monitoring dashboard.
"""

import streamlit as st
from datetime import date, timedelta
from config import (
    DATE_PRESETS, DATA_LAG_DAYS, DEFAULT_PRESET, BRAND_NAVY,
    SECTIONS, DEFAULT_SECTION, GRANULARITY_OPTIONS, SMOOTHING_OPTIONS,
)

st.set_page_config(page_title="Binaytara SEO Monitor", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown(f"""
<style>
    .stMetric {{
        background: {BRAND_NAVY}08; padding: 12px 16px;
        border-radius: 8px; border-left: 4px solid {BRAND_NAVY};
    }}
    .stTabs [data-baseweb="tab"] {{ padding: 8px 18px; font-weight: 500; }}
    div[data-testid="stMetricValue"] {{ font-size: 1.5rem; font-weight: 600; }}
</style>
""", unsafe_allow_html=True)

# ── Sidebar: global controls ──────────────────────────────────────
with st.sidebar:
    st.markdown(f'<h2 style="color:{BRAND_NAVY};margin-bottom:0;">📊 Binaytara</h2>', unsafe_allow_html=True)
    st.markdown('<p style="color:#666;font-size:13px;margin-top:0;">SEO Monitor</p>', unsafe_allow_html=True)
    st.divider()

    st.markdown("**📅 Date range**")
    preset = st.selectbox("Period", list(DATE_PRESETS.keys()),
                          index=list(DATE_PRESETS.keys()).index(DEFAULT_PRESET))
    today = date.today()
    safe_end = today - timedelta(days=DATA_LAG_DAYS)

    if preset == "Custom":
        a, b = st.columns(2)
        with a:
            curr_start = st.date_input("Current start", value=safe_end - timedelta(days=27), max_value=safe_end)
        with b:
            curr_end = st.date_input("Current end", value=safe_end, max_value=safe_end)
        st.markdown("<small style='color:#666;'>compared with</small>", unsafe_allow_html=True)
        c, d = st.columns(2)
        with c:
            prev_start = st.date_input("Compare start",
                                       value=curr_start - timedelta(days=(curr_end - curr_start).days + 1),
                                       max_value=safe_end)
        with d:
            prev_end = st.date_input("Compare end", value=curr_start - timedelta(days=1), max_value=safe_end)
        if curr_start > curr_end:
            st.error("Current start must be before end.")
        if prev_start > prev_end:
            st.error("Compare start must be before end.")
        cd, pd_ = (curr_end - curr_start).days, (prev_end - prev_start).days
        if cd != pd_:
            st.caption(f"Lengths differ: current {cd+1}d vs compare {pd_+1}d (allowed — periods are independent).")
    else:
        days = DATE_PRESETS[preset]
        curr_end = safe_end
        curr_start = safe_end - timedelta(days=days - 1)
        prev_end = curr_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)
        st.caption(f"Current: {curr_start} to {curr_end}")
        st.caption(f"Compare: {prev_start} to {prev_end}")

    dates = {"curr_start": str(curr_start), "curr_end": str(curr_end),
             "prev_start": str(prev_start), "prev_end": str(prev_end)}

    show_comparison = st.checkbox("Compare with previous period", value=True)
    dates["show_comparison"] = show_comparison
    st.divider()

    st.markdown("**📈 Chart controls**")
    granularity = st.radio("Granularity", GRANULARITY_OPTIONS, index=0, horizontal=True)
    smoothing = st.selectbox("Smoothing (daily only)", SMOOTHING_OPTIONS, index=0)
    hero_split = st.checkbox("Split hero by section", value=False)
    hero_show_impr = st.checkbox("Show impressions on hero", value=False)
    controls = {"granularity": granularity, "smoothing": smoothing,
                "hero_split_section": hero_split, "hero_show_impressions": hero_show_impr}
    st.divider()

    st.markdown("**📊 Traffic type**")
    traffic_type = st.radio("Show", ["Organic Traffic", "Total Traffic"], index=0, horizontal=True)
    organic_only = traffic_type == "Organic Traffic"
    st.divider()

    st.markdown("**🏷 Sections**")
    section_names = ["All Sections"] + [s["name"] for s in SECTIONS] + [DEFAULT_SECTION]
    section_filter = st.multiselect("Study these sections", section_names, default=["All Sections"])
    if not section_filter:
        section_filter = ["All Sections"]
    st.divider()

    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(f"Data as of: {safe_end} (recent partial days excluded)")

# ── Header: plain-language active state ────────────────────────────
scope = "All sections" if "All Sections" in section_filter else " + ".join(section_filter)
state = (f'{"Organic" if organic_only else "Total"} · {granularity} · '
         f'{dates["curr_start"]} to {dates["curr_end"]}'
         f'{" vs " + dates["prev_start"] + " to " + dates["prev_end"] if show_comparison else ""} · {scope}')
st.markdown(f'<h1 style="color:{BRAND_NAVY};font-size:1.7rem;margin-bottom:2px;">Binaytara SEO Monitor</h1>',
            unsafe_allow_html=True)
st.markdown(f'<p style="color:#666;font-size:13px;margin-top:0;">{state}</p>', unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Overview", "🔎 Search Performance", "📄 Pages",
    "🧭 Keyword Deep Dive", "💡 Opportunities",
])

try:
    with tab1:
        from tabs.overview import render as render_overview
        render_overview(dates, organic_only, section_filter, controls)
    with tab2:
        from tabs.search_performance import render as render_search
        render_search(dates, organic_only, section_filter, controls)
    with tab3:
        from tabs.pages import render as render_pages
        render_pages(dates, organic_only, section_filter)
    with tab4:
        from tabs.keywords import render as render_keywords
        render_keywords(dates, organic_only, section_filter)
    with tab5:
        from tabs.opportunities import render as render_opportunities
        render_opportunities(dates, organic_only, section_filter)
except Exception as e:
    st.error(f"An error occurred: {e}")
    st.caption("Check that the service account has Viewer on GA4 (property 468739074) and "
               "Full access on GSC (sc-domain:binaytara.org).")
    with st.expander("Error details"):
        import traceback
        st.code(traceback.format_exc())
