"""
Binaytara SEO Monitor — Tab 2: Page Performance
Page-level traffic comparison table with GSC data.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from config import BRAND_NAVY, BRAND_GREEN, BRAND_RED, SITE_DOMAIN
from data.processing import join_ga4_gsc, signal_label
from export import to_excel_bytes, make_filename


def render(dates: dict, organic_only: bool, section_filter: list[str]):
    """Main render function for the Page Performance tab."""
    from data.ga4 import fetch_page_traffic
    from data.gsc import fetch_gsc_page_summary

    curr_start, curr_end = dates["curr_start"], dates["curr_end"]
    prev_start, prev_end = dates["prev_start"], dates["prev_end"]
    show_comparison = dates.get("show_comparison", True)

    # ── Fetch data ───────────────────────────────────────────
    with st.spinner("Loading page performance data..."):
        curr_pages = fetch_page_traffic(curr_start, curr_end, organic_only)
        prev_pages = fetch_page_traffic(prev_start, prev_end, organic_only) if show_comparison else pd.DataFrame()
        gsc_data = fetch_gsc_page_summary(curr_start, curr_end)

    if curr_pages.empty:
        st.warning("No page data found for the selected date range.")
        return

    # ── Build comparison table ───────────────────────────────
    table = curr_pages[["page_path", "section", "totalUsers", "sessions"]].copy()
    table.rename(columns={"totalUsers": "users_current", "sessions": "sessions_current"}, inplace=True)

    if show_comparison and not prev_pages.empty:
        prev_agg = prev_pages[["page_path", "totalUsers"]].rename(columns={"totalUsers": "users_previous"})
        table = table.merge(prev_agg, on="page_path", how="left").fillna(0)
        table["users_previous"] = table["users_previous"].astype(int)
        table["users_change"] = table["users_current"] - table["users_previous"]
        table["users_pct_change"] = table.apply(
            lambda r: (r["users_change"] / r["users_previous"] * 100) if r["users_previous"] > 0 else None, axis=1
        )
        table["signal"] = table.apply(
            lambda r: signal_label(r["users_current"], r["users_previous"]), axis=1
        )
    else:
        table["users_previous"] = 0
        table["users_change"] = 0
        table["users_pct_change"] = None
        table["signal"] = "—"

    # Join GSC data
    table = join_ga4_gsc(table, gsc_data)

    # Apply section filter
    if section_filter and "All Sections" not in section_filter:
        table = table[table["section"].isin(section_filter)]

    # ── Row 1: Quick Stats ───────────────────────────────────
    growing = len(table[table["users_change"] > 0])
    declining = len(table[table["users_change"] < 0])
    stable = len(table[table["users_change"] == 0])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Pages", f"{len(table):,}")
    c2.metric("📈 Growing", f"{growing:,}")
    c3.metric("📉 Declining", f"{declining:,}")
    c4.metric("→ Stable", f"{stable:,}")

    st.divider()

    # ── Row 2: Top Gainers / Losers ──────────────────────────
    if show_comparison:
        col_gain, col_loss = st.columns(2)

        with col_gain:
            st.markdown("**Top 5 Growing Pages**")
            top_gain = table.nlargest(5, "users_change")
            for _, row in top_gain.iterrows():
                path_display = row["page_path"][:60]
                change = int(row["users_change"])
                pct = row["users_pct_change"]
                pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
                st.markdown(
                    f'<div style="padding:6px 10px; margin:3px 0; background:#E2EFDA; border-radius:6px; font-size:13px;">'
                    f'<b>{path_display}</b><br>'
                    f'<span style="color:#1E7E34;">+{change:,} users{pct_str}</span></div>',
                    unsafe_allow_html=True,
                )

        with col_loss:
            st.markdown("**Top 5 Declining Pages**")
            top_loss = table.nsmallest(5, "users_change")
            for _, row in top_loss.iterrows():
                path_display = row["page_path"][:60]
                change = int(row["users_change"])
                pct = row["users_pct_change"]
                pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
                st.markdown(
                    f'<div style="padding:6px 10px; margin:3px 0; background:#FFF2CC; border-radius:6px; font-size:13px;">'
                    f'<b>{path_display}</b><br>'
                    f'<span style="color:#DC3545;">{change:,} users{pct_str}</span></div>',
                    unsafe_allow_html=True,
                )

        st.divider()

    # ── Row 3: Full Page Table ───────────────────────────────
    st.subheader("Page Performance Table")

    # Search filter
    search = st.text_input("🔍 Filter by page path", placeholder="e.g. cancernews, stomach-cancer, conferences")
    if search:
        table = table[table["page_path"].str.contains(search, case=False, na=False)]

    # Sort options
    sort_col = st.selectbox("Sort by", [
        "Users Change (biggest drops first)",
        "Current Users (highest first)",
        "GSC Impressions (highest first)",
        "GSC CTR (lowest first)",
    ], index=0)

    sort_map = {
        "Users Change (biggest drops first)": ("users_change", True),
        "Current Users (highest first)": ("users_current", False),
        "GSC Impressions (highest first)": ("gsc_impressions", False),
        "GSC CTR (lowest first)": ("gsc_ctr", True),
    }
    s_col, s_asc = sort_map[sort_col]
    if s_col in table.columns:
        table = table.sort_values(s_col, ascending=s_asc, na_position="last")

    # Build display DataFrame
    display_df = pd.DataFrame()
    display_df["Page"] = table["page_path"]
    display_df["Section"] = table["section"]
    display_df["Users (Current)"] = table["users_current"]
    if show_comparison:
        display_df["Users (Previous)"] = table["users_previous"]
        display_df["Users Change"] = table["users_change"]
        display_df["% Change"] = table["users_pct_change"]
    display_df["Sessions"] = table["sessions_current"]
    if "gsc_clicks" in table.columns:
        display_df["GSC Clicks"] = table["gsc_clicks"]
        display_df["GSC Impressions"] = table["gsc_impressions"]
        display_df["GSC CTR"] = table["gsc_ctr"]
        display_df["GSC Avg Position"] = table["gsc_position"]
    if show_comparison:
        display_df["Signal"] = table["signal"]

    # Column config
    col_config = {
        "Page": st.column_config.TextColumn(width="large"),
        "GSC CTR": st.column_config.NumberColumn(format="%.2f%%"),
        "GSC Avg Position": st.column_config.NumberColumn(format="%.1f"),
        "% Change": st.column_config.NumberColumn(format="%.1f%%"),
    }

    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=col_config,
        on_select="rerun",
        selection_mode="single-row",
    )

    # Handle row selection for drill-down
    if event and event.selection and event.selection.rows:
        selected_idx = event.selection.rows[0]
        if selected_idx < len(display_df):
            selected_path = display_df.iloc[selected_idx]["Page"]
            st.session_state["selected_page"] = selected_path
            st.info(f"Selected: **{selected_path}** — switch to the Keyword Deep Dive tab to see query data.")

    # Export
    meta = f"Binaytara SEO Monitor | Current: {curr_start} to {curr_end} | Previous: {prev_start} to {prev_end}"
    xlsx = to_excel_bytes(display_df, "Page Performance", meta)
    fname = make_filename("page_performance", curr_start, curr_end)
    st.download_button("📥 Export Page Table", data=xlsx, file_name=fname,
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.divider()

    # ── Row 4: Scatter Plot (CTR vs Impressions) ─────────────
    if "gsc_impressions" in table.columns:
        scatter_df = table.dropna(subset=["gsc_impressions", "gsc_ctr"])
        scatter_df = scatter_df[scatter_df["gsc_impressions"] > 0]

        if not scatter_df.empty:
            st.subheader("CTR vs Impressions")
            fig = px.scatter(
                scatter_df,
                x="gsc_impressions",
                y="gsc_ctr",
                size="users_current",
                color="section",
                hover_name="page_path",
                title="Pages by Impressions vs CTR (size = users)",
                labels={"gsc_impressions": "Impressions", "gsc_ctr": "CTR", "users_current": "Users"},
                color_discrete_sequence=["#1B3A6B", "#2E5BA8", "#5577AA", "#7799CC", "#AABBDD"],
            )
            fig.update_layout(height=450, margin=dict(l=40, r=20, t=50, b=30))
            fig.update_yaxes(tickformat=".1%")
            st.plotly_chart(fig, use_container_width=True)

    st.caption("GA4 verification: Reports → Engagement → Landing Page → filter Default Channel Group = Organic Search")
