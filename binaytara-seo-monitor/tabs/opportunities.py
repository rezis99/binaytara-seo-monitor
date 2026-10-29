"""
Binaytara SEO Monitor — Tab 4: Opportunities
CTR candidates, striking distance, declining pages, growing content.
"""

import streamlit as st
import pandas as pd
from config import (
    BRAND_NAVY, BRAND_GREEN, BRAND_RED, SITE_DOMAIN,
    CTR_OPP_MIN_IMPRESSIONS, CTR_OPP_MAX_CTR,
    STRIKING_MIN_POSITION, STRIKING_MAX_POSITION, STRIKING_MIN_IMPRESSIONS,
    DECLINE_MIN_CHANGE_PCT, DECLINE_MIN_PREV_USERS,
    GROWTH_MIN_CHANGE_PCT, GROWTH_MIN_CURR_USERS,
)
from data.processing import join_ga4_gsc, signal_label
from export import to_excel_bytes, make_filename


def render(dates: dict, organic_only: bool, section_filter: list[str]):
    """Main render function for the Opportunities tab."""
    from data.ga4 import fetch_page_traffic
    from data.gsc import fetch_gsc_page_summary

    curr_start, curr_end = dates["curr_start"], dates["curr_end"]
    prev_start, prev_end = dates["prev_start"], dates["prev_end"]
    show_comparison = dates.get("show_comparison", True)

    with st.spinner("Loading opportunity data..."):
        curr_pages = fetch_page_traffic(curr_start, curr_end, organic_only)
        prev_pages = fetch_page_traffic(prev_start, prev_end, organic_only) if show_comparison else pd.DataFrame()
        gsc_data = fetch_gsc_page_summary(curr_start, curr_end)

    if curr_pages.empty:
        st.warning("No data available for the selected date range.")
        return

    # ── Build merged dataset ─────────────────────────────────
    table = curr_pages[["page_path", "section", "totalUsers", "sessions"]].copy()
    table.rename(columns={"totalUsers": "users_current", "sessions": "sessions_current"}, inplace=True)

    if show_comparison and not prev_pages.empty:
        prev_agg = prev_pages[["page_path", "totalUsers"]].rename(columns={"totalUsers": "users_previous"})
        table = table.merge(prev_agg, on="page_path", how="left").fillna(0)
        table["users_previous"] = table["users_previous"].astype(int)
        table["users_change"] = table["users_current"] - table["users_previous"]
        table["users_pct_change"] = table.apply(
            lambda r: r["users_change"] / r["users_previous"] if r["users_previous"] > 0 else None, axis=1
        )
    else:
        table["users_previous"] = 0
        table["users_change"] = 0
        table["users_pct_change"] = None

    table = join_ga4_gsc(table, gsc_data)

    # Apply section filter
    if section_filter and "All Sections" not in section_filter:
        table = table[table["section"].isin(section_filter)]

    # ── Section A: CTR Optimization ──────────────────────────
    st.subheader("🎯 CTR Optimization Candidates")
    st.caption(f"Pages with {CTR_OPP_MIN_IMPRESSIONS}+ impressions and CTR below {CTR_OPP_MAX_CTR*100:.0f}%. Optimize meta titles and descriptions.")

    if "gsc_impressions" in table.columns and "gsc_ctr" in table.columns:
        ctr_df = table[
            (table["gsc_impressions"] >= CTR_OPP_MIN_IMPRESSIONS) &
            (table["gsc_ctr"].notna()) &
            (table["gsc_ctr"] < CTR_OPP_MAX_CTR)
        ].copy()
        ctr_df = ctr_df.sort_values("gsc_impressions", ascending=False)

        if not ctr_df.empty:
            # Add suggested action
            def suggest_action(row):
                pos = row.get("gsc_position", 50)
                if pos is None or pd.isna(pos):
                    return "Investigate further"
                if pos < 5:
                    return "Optimize meta title and description"
                if pos <= 10:
                    return "Improve content depth and optimize meta"
                return "Content needs significant improvement"

            ctr_df["suggested_action"] = ctr_df.apply(suggest_action, axis=1)

            display = ctr_df[["page_path", "section", "gsc_impressions", "gsc_clicks", "gsc_ctr", "gsc_position", "suggested_action"]].copy()
            display.columns = ["Page", "Section", "Impressions", "Clicks", "CTR", "Avg Position", "Suggested Action"]

            st.dataframe(display, use_container_width=True, hide_index=True,
                        column_config={
                            "Page": st.column_config.TextColumn(width="large"),
                            "CTR": st.column_config.NumberColumn(format="%.2f%%"),
                            "Avg Position": st.column_config.NumberColumn(format="%.1f"),
                        })

            meta = f"Binaytara SEO Monitor | CTR Opportunities | {curr_start} to {curr_end}"
            xlsx = to_excel_bytes(display, "CTR Opportunities", meta)
            st.download_button("📥 Export CTR Candidates", data=xlsx,
                              file_name=make_filename("ctr_opportunities", curr_start, curr_end),
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.success("No CTR optimization candidates found. All high-impression pages have healthy CTR.")
    else:
        st.info("GSC data not available. Connect GSC to see CTR opportunities.")

    st.divider()

    # ── Section B: Striking Distance ─────────────────────────
    st.subheader("🎯 Striking Distance Pages")
    from config import STRIKING_BAND_PRESETS
    band_label = st.selectbox(
        "Striking-distance band", list(STRIKING_BAND_PRESETS.keys()), index=0,
        help="The agency standard is positions 11–20 (page two). 8–20 is a common wider "
             "variant; 4–15 is the AI-era version. Position here is an impression-weighted "
             "average, so treat the list as a shortlist to check rather than an exact rank.")
    band_min, band_max = STRIKING_BAND_PRESETS[band_label]
    st.caption(f"Pages whose average position is {band_min}–{band_max} with "
               f"{STRIKING_MIN_IMPRESSIONS}+ impressions. Small improvements could push these up a page.")

    if "gsc_position" in table.columns:
        strike_df = table[
            (table["gsc_position"] >= band_min) &
            (table["gsc_position"] <= band_max) &
            (table["gsc_impressions"] >= STRIKING_MIN_IMPRESSIONS)
        ].copy()
        strike_df = strike_df.sort_values("gsc_impressions", ascending=False).head(30)

        if not strike_df.empty:
            # Estimate potential clicks if top 3 (conservative 10% CTR)
            strike_df["estimated_clicks_top3"] = (strike_df["gsc_impressions"] * 0.10).astype(int)
            strike_df["potential_gain"] = strike_df["estimated_clicks_top3"] - strike_df["gsc_clicks"].fillna(0).astype(int)

            display = strike_df[["page_path", "section", "gsc_position", "gsc_impressions", "gsc_clicks", "estimated_clicks_top3", "potential_gain"]].copy()
            display.columns = ["Page", "Section", "Avg Position", "Impressions", "Current Clicks", "Est. Clicks if Top 3", "Potential Gain"]

            st.dataframe(display, use_container_width=True, hide_index=True,
                        column_config={
                            "Page": st.column_config.TextColumn(width="large"),
                            "Avg Position": st.column_config.NumberColumn(format="%.1f"),
                        })

            meta = f"Binaytara SEO Monitor | Striking Distance | {curr_start} to {curr_end}"
            xlsx = to_excel_bytes(display, "Striking Distance", meta)
            st.download_button("📥 Export Striking Distance", data=xlsx,
                              file_name=make_filename("striking_distance", curr_start, curr_end),
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.success("No striking distance pages found with current thresholds.")
    else:
        st.info("GSC data not available.")

    st.divider()

    # ── Section C: Declining Pages ───────────────────────────
    if show_comparison:
        st.subheader("📉 Declining Pages That Need Attention")
        st.caption(f"Pages with traffic decline > {abs(DECLINE_MIN_CHANGE_PCT)*100:.0f}% and at least {DECLINE_MIN_PREV_USERS} previous users.")

        decline_df = table[
            (table["users_pct_change"].notna()) &
            (table["users_pct_change"] < DECLINE_MIN_CHANGE_PCT) &
            (table["users_previous"] >= DECLINE_MIN_PREV_USERS)
        ].copy()
        decline_df = decline_df.sort_values("users_change", ascending=True)

        if not decline_df.empty:
            # Attempt automated diagnosis
            def diagnose(row):
                gsc_pos = row.get("gsc_position")
                # We don't have previous GSC position in page-level data,
                # so we use a simplified diagnosis based on available data
                if row.get("gsc_impressions") is not None and row["gsc_impressions"] == 0:
                    return "Impression loss (possible deindexing)"
                if gsc_pos is not None and gsc_pos > 20:
                    return "Ranking drop (position > 20)"
                if row.get("gsc_ctr") is not None and row["gsc_ctr"] < 0.01:
                    return "CTR issue (below 1%)"
                path = str(row.get("page_path", ""))
                if "/projects/conferences/" in path:
                    return "Possible seasonal (conference page)"
                return "Investigate further"

            decline_df["likely_cause"] = decline_df.apply(diagnose, axis=1)

            display = decline_df[["page_path", "section", "users_current", "users_previous", "users_change", "users_pct_change", "likely_cause"]].copy()
            display.columns = ["Page", "Section", "Users (Current)", "Users (Previous)", "Change", "% Change", "Likely Cause"]
            display["% Change"] = display["% Change"].apply(lambda x: f"{x*100:.1f}%" if x is not None else "")

            st.dataframe(display, use_container_width=True, hide_index=True,
                        column_config={"Page": st.column_config.TextColumn(width="large")})

            meta = f"Binaytara SEO Monitor | Declining Pages | Current: {curr_start} to {curr_end} | Previous: {prev_start} to {prev_end}"
            xlsx = to_excel_bytes(display, "Declining Pages", meta)
            st.download_button("📥 Export Declining Pages", data=xlsx,
                              file_name=make_filename("declining_pages", curr_start, curr_end),
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.success("No significantly declining pages found. Traffic is stable or growing across the board.")

        st.divider()

    # ── Section D: Growing Content ───────────────────────────
    if show_comparison:
        st.subheader("📈 Growing Content to Double Down On")
        st.caption(f"Pages with > {GROWTH_MIN_CHANGE_PCT*100:.0f}% traffic growth and at least {GROWTH_MIN_CURR_USERS} current users.")

        growth_df = table[
            (table["users_pct_change"].notna()) &
            (table["users_pct_change"] > GROWTH_MIN_CHANGE_PCT) &
            (table["users_current"] >= GROWTH_MIN_CURR_USERS)
        ].copy()
        growth_df = growth_df.sort_values("users_pct_change", ascending=False)

        if not growth_df.empty:
            display = growth_df[["page_path", "section", "users_current", "users_previous", "users_pct_change"]].copy()
            display.columns = ["Page", "Section", "Users (Current)", "Users (Previous)", "% Change"]
            display["% Change"] = display["% Change"].apply(lambda x: f"+{x*100:.1f}%" if x is not None else "")

            st.dataframe(display, use_container_width=True, hide_index=True,
                        column_config={"Page": st.column_config.TextColumn(width="large")})
        else:
            st.info("No pages with significant growth found for the current thresholds.")

    st.caption("GA4 verification: Reports → Engagement → Landing Page → filter Organic Search → sort by Users")
