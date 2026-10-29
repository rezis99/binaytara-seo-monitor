"""
Binaytara SEO Monitor — Tab 3: Keyword Deep Dive
Per-page GSC query analysis with New/Lost/Retained detection.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from config import SITE_DOMAIN, BRAND_NAVY, BRAND_GREEN, BRAND_RED
from export import to_excel_bytes, make_filename


def render(dates: dict, organic_only: bool, section_filter: list[str]):
    """Main render function for the Keyword Deep Dive tab."""
    from data.ga4 import fetch_page_traffic
    from data.gsc import compare_queries, fetch_gsc_page_summary

    curr_start, curr_end = dates["curr_start"], dates["curr_end"]
    prev_start, prev_end = dates["prev_start"], dates["prev_end"]

    # ── Page selector ────────────────────────────────────────
    with st.spinner("Loading page list..."):
        gsc_summary = fetch_gsc_page_summary(curr_start, curr_end)

    if gsc_summary.empty:
        st.warning("No GSC data available for the selected date range.")
        return

    # Build page list sorted by clicks
    page_list = gsc_summary.sort_values("gsc_clicks", ascending=False)["page"].tolist()

    # Pre-select from Tab 2 if available
    default_idx = 0
    preselected = st.session_state.get("selected_page", "")
    if preselected:
        # Convert path to full URL for matching
        full_url = SITE_DOMAIN + preselected
        matching = [i for i, p in enumerate(page_list) if p == full_url or p.rstrip("/") == full_url.rstrip("/")]
        if matching:
            default_idx = matching[0]

    selected_page = st.selectbox(
        "Select a page to investigate",
        page_list,
        index=default_idx,
        format_func=lambda x: x.replace(SITE_DOMAIN, ""),
    )

    if not selected_page:
        st.info("Select a page above to see its keyword data.")
        return

    # ── Fetch query comparison ───────────────────────────────
    with st.spinner(f"Fetching keyword data for {selected_page.replace(SITE_DOMAIN, '')}..."):
        query_df = compare_queries(selected_page, curr_start, curr_end, prev_start, prev_end)

    if query_df.empty:
        st.warning("No query data found for this page in either period.")
        return

    # ── Page summary line ────────────────────────────────────
    total_clicks_curr = query_df["clicks_current"].sum()
    total_clicks_prev = query_df["clicks_previous"].sum()
    clicks_change = total_clicks_curr - total_clicks_prev
    clicks_pct = (clicks_change / total_clicks_prev * 100) if total_clicks_prev > 0 else 0

    path_display = selected_page.replace(SITE_DOMAIN, "")
    st.markdown(
        f"**Page:** `{path_display}` &nbsp;|&nbsp; "
        f"**Current Clicks:** {total_clicks_curr:,} &nbsp;|&nbsp; "
        f"**Previous Clicks:** {total_clicks_prev:,} &nbsp;|&nbsp; "
        f"**Change:** {clicks_change:+,} ({clicks_pct:+.1f}%)"
    )

    st.divider()

    # ── Summary metrics ──────────────────────────────────────
    total_queries = len(query_df)
    new_queries = len(query_df[query_df["status"] == "New"])
    lost_queries = len(query_df[query_df["status"] == "Lost"])
    net_change = new_queries - lost_queries

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Queries", f"{total_queries:,}")
    c2.metric("🆕 New Queries", f"{new_queries:,}")
    c3.metric("❌ Lost Queries", f"{lost_queries:,}")
    c4.metric("Net Query Change", f"{net_change:+,}",
              delta=f"{net_change:+,}", delta_color="normal")

    st.divider()

    # ── Query table ──────────────────────────────────────────
    st.subheader("Query Data")

    # Status filter
    status_filter = st.multiselect(
        "Filter by status",
        ["New", "Lost", "Retained"],
        default=["New", "Lost", "Retained"],
    )
    filtered = query_df[query_df["status"].isin(status_filter)]

    # Build display DataFrame
    display_df = pd.DataFrame()
    display_df["Query"] = filtered["query"]
    display_df["Status"] = filtered["status"]
    display_df["Clicks (Current)"] = filtered["clicks_current"]
    display_df["Clicks (Previous)"] = filtered["clicks_previous"]
    display_df["Clicks Change"] = filtered["clicks_change"]
    display_df["Impr (Current)"] = filtered["impressions_current"]
    display_df["Impr (Previous)"] = filtered["impressions_previous"]
    display_df["Impr Change"] = filtered["impressions_change"]
    display_df["CTR (Current)"] = filtered["ctr_current"]
    display_df["CTR (Previous)"] = filtered["ctr_previous"]
    display_df["Pos (Current)"] = filtered["position_current"]
    display_df["Pos (Previous)"] = filtered["position_previous"]
    display_df["Pos Change"] = filtered["position_change"]

    col_config = {
        "Query": st.column_config.TextColumn(width="large"),
        "CTR (Current)": st.column_config.NumberColumn(format="%.2f%%"),
        "CTR (Previous)": st.column_config.NumberColumn(format="%.2f%%"),
        "Pos (Current)": st.column_config.NumberColumn(format="%.1f"),
        "Pos (Previous)": st.column_config.NumberColumn(format="%.1f"),
        "Pos Change": st.column_config.NumberColumn(format="%.1f"),
    }

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=col_config,
    )

    # Note about row limit
    if len(query_df) >= 1000:
        st.caption("Showing top 1,000 queries by clicks. Some low-traffic queries may not appear.")

    # Export
    slug = path_display.rstrip("/").split("/")[-1][:50]
    meta = f"Binaytara SEO Monitor | Page: {path_display} | Current: {curr_start} to {curr_end} | Previous: {prev_start} to {prev_end}"
    xlsx = to_excel_bytes(display_df, "Keywords", meta)
    fname = make_filename("keywords", curr_start, curr_end, page_slug=path_display)
    st.download_button("📥 Export Keywords", data=xlsx, file_name=fname,
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.divider()

    # ── Position Distribution Chart ──────────────────────────
    retained = filtered[filtered["status"] == "Retained"].copy()
    if not retained.empty and retained["position_current"].notna().any():
        st.subheader("Position Distribution (Retained Queries)")

        pos_data = retained["position_current"].dropna()

        def pos_bucket(p):
            if p <= 3: return "1–3 (Top 3)"
            if p <= 10: return "4–10 (Page 1)"
            if p <= 20: return "11–20 (Page 2)"
            if p <= 50: return "21–50"
            return "51–100"

        buckets = pos_data.apply(pos_bucket)
        bucket_order = ["1–3 (Top 3)", "4–10 (Page 1)", "11–20 (Page 2)", "21–50", "51–100"]
        bucket_counts = buckets.value_counts().reindex(bucket_order, fill_value=0)

        fig = px.bar(
            x=bucket_counts.index,
            y=bucket_counts.values,
            title="Current Position Distribution",
            labels={"x": "Position Range", "y": "Query Count"},
            color_discrete_sequence=[BRAND_NAVY],
        )
        fig.update_layout(height=300, margin=dict(l=40, r=20, t=50, b=30), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.caption("GSC verification: Performance → Pages → filter by this URL → compare date ranges")
