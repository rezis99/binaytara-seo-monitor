"""
Binaytara SEO Monitor — Tab: Overview
Run-rate scorecards, rolling 28-day (monthly-scale) hero, exact daily trend,
growth/decline movers, section split, and geography by country.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from config import (
    BRAND_NAVY, BRAND_GREEN, BRAND_RED, BRAND_GRAY, SECTION_COLORS,
    ROLLING_WINDOW_DAYS,
)
from data.processing import (
    join_ga4_gsc, rolling_total, resample_timeseries, apply_smoothing,
)
from export import to_excel_bytes, make_filename


def _wmean(df, col, weight):
    w = df[weight].sum()
    return (df[col] * df[weight]).sum() / w if w else None


def _section_mask(df, section_filter):
    if section_filter and "All Sections" not in section_filter:
        return df[df["section"].isin(section_filter)]
    return df


def render(dates, organic_only, section_filter, controls=None):
    from data.ga4 import (
        fetch_daily_traffic, fetch_page_traffic,
        fetch_daily_by_section, fetch_country_traffic,
    )
    from data.gsc import fetch_gsc_daily_totals, fetch_gsc_page_summary

    controls = controls or {}
    granularity = controls.get("granularity", "Daily")
    smoothing = controls.get("smoothing", "Raw")
    hero_split = controls.get("hero_split_section", False)
    show_impr = controls.get("hero_show_impressions", False)

    cs, ce = dates["curr_start"], dates["curr_end"]
    ps, pe = dates["prev_start"], dates["prev_end"]
    show_cmp = dates.get("show_comparison", True)
    section_active = bool(section_filter) and "All Sections" not in section_filter
    scope_label = " + ".join(section_filter) if section_active else "All sections"

    with st.spinner("Loading overview data..."):
        g_daily_c = fetch_gsc_daily_totals(cs, ce)
        ga_daily_c = fetch_daily_traffic(cs, ce, organic_only)
        pages_c = fetch_page_traffic(cs, ce, organic_only)
        gsc_pages_c = fetch_gsc_page_summary(cs, ce)
        if show_cmp:
            pages_p = fetch_page_traffic(ps, pe, organic_only)
            gsc_pages_p = fetch_gsc_page_summary(ps, pe)
        else:
            pages_p, gsc_pages_p = pd.DataFrame(), pd.DataFrame()

    if ga_daily_c.empty and g_daily_c.empty:
        st.warning("No data found for the selected date range. Check GA4/GSC access and the dates.")
        return

    # ── Section-aware page-level joins (used for scorecards + section table) ──
    joined_c = join_ga4_gsc(
        pages_c[["page_path", "section", "totalUsers", "sessions"]]
        .rename(columns={"totalUsers": "users", "sessions": "sessions"}),
        gsc_pages_c,
    )
    joined_c = _section_mask(joined_c, section_filter)

    if show_cmp and not pages_p.empty:
        joined_p = join_ga4_gsc(
            pages_p[["page_path", "section", "totalUsers", "sessions"]]
            .rename(columns={"totalUsers": "users"}),
            gsc_pages_p,
        )
        joined_p = _section_mask(joined_p, section_filter)
    else:
        joined_p = pd.DataFrame()

    def _nz(series):
        return pd.to_numeric(series, errors="coerce").fillna(0)

    cur = {
        "users": int(_nz(joined_c.get("users", pd.Series(dtype=float))).sum()),
        "clicks": int(_nz(joined_c.get("gsc_clicks", pd.Series(dtype=float))).sum()),
        "impr": int(_nz(joined_c.get("gsc_impressions", pd.Series(dtype=float))).sum()),
    }
    cur["ctr"] = (cur["clicks"] / cur["impr"]) if cur["impr"] else 0
    cur["pos"] = _wmean(joined_c.assign(_i=_nz(joined_c.get("gsc_impressions", 0)),
                                        _p=_nz(joined_c.get("gsc_position", 0))), "_p", "_i") \
        if not joined_c.empty else None

    if not joined_p.empty:
        prev = {
            "users": int(_nz(joined_p.get("users", pd.Series(dtype=float))).sum()),
            "clicks": int(_nz(joined_p.get("gsc_clicks", pd.Series(dtype=float))).sum()),
            "impr": int(_nz(joined_p.get("gsc_impressions", pd.Series(dtype=float))).sum()),
        }
        prev["ctr"] = (prev["clicks"] / prev["impr"]) if prev["impr"] else 0
        prev["pos"] = _wmean(joined_p.assign(_i=_nz(joined_p.get("gsc_impressions", 0)),
                                             _p=_nz(joined_p.get("gsc_position", 0))), "_p", "_i")
    else:
        prev = None

    # ── Row 1: Run-rate scorecards (growth green, decline red) ──
    st.markdown(f"**Run rate — {scope_label}**")
    c1, c2, c3, c4, c5 = st.columns(5)

    def _delta(curval, prevval):
        if not show_cmp or prev is None or prevval in (None, 0):
            return None
        return curval - prevval

    with c1:
        d = _delta(cur["clicks"], prev["clicks"] if prev else None)
        st.metric("Organic clicks", f"{cur['clicks']:,}", delta=f"{d:+,}" if d is not None else None)
    with c2:
        d = _delta(cur["users"], prev["users"] if prev else None)
        st.metric("Organic users", f"{cur['users']:,}", delta=f"{d:+,}" if d is not None else None)
    with c3:
        d = _delta(cur["impr"], prev["impr"] if prev else None)
        st.metric("Impressions", f"{cur['impr']:,}", delta=f"{d:+,}" if d is not None else None)
    with c4:
        if prev and show_cmp and prev["ctr"]:
            dctr = (cur["ctr"] - prev["ctr"]) * 100
            st.metric("CTR", f"{cur['ctr']*100:.2f}%", delta=f"{dctr:+.2f} pts")
        else:
            st.metric("CTR", f"{cur['ctr']*100:.2f}%")
    with c5:
        if cur["pos"] is not None:
            if prev and show_cmp and prev["pos"] is not None:
                dpos = cur["pos"] - prev["pos"]  # lower is better
                st.metric("Avg position", f"{cur['pos']:.1f}", delta=f"{dpos:+.1f}", delta_color="inverse")
            else:
                st.metric("Avg position", f"{cur['pos']:.1f}")
        else:
            st.metric("Avg position", "—")

    st.caption(
        "Clicks, impressions, CTR and average position come from Google Search Console; "
        "users from GA4. Average position is impression-weighted (an average across all "
        "impressions, not a daily rank). Recent partial days are excluded automatically."
    )
    st.divider()

    # ── Row 2: Hero — rolling 28-day total (monthly scale) ──
    st.subheader("Monthly-scale trend (rolling 28-day total)")
    hero = go.Figure()

    if hero_split and not g_daily_c.empty or hero_split:
        sec_daily = fetch_daily_by_section(cs, ce, organic_only)
        sec_daily = _section_mask(sec_daily, section_filter)
        if not sec_daily.empty:
            pivot = sec_daily.pivot_table(index="date", columns="section",
                                          values="totalUsers", aggfunc="sum").fillna(0).sort_index()
            for sec in pivot.columns:
                roll = rolling_total(pivot[sec], ROLLING_WINDOW_DAYS)
                hero.add_trace(go.Scatter(
                    x=pivot.index, y=roll, mode="lines", name=sec,
                    line=dict(color=SECTION_COLORS.get(sec, BRAND_GRAY), width=2),
                ))
        hero_caption = ("Each line = that section's trailing 28-day organic-user total "
                        "(GA4). Begins 27 days after the range start.")
    else:
        merged = pd.DataFrame()
        if not g_daily_c.empty:
            merged = g_daily_c[["date", "clicks", "impressions"]].copy()
        if not ga_daily_c.empty:
            u = ga_daily_c[["date", "totalUsers"]].rename(columns={"totalUsers": "users"})
            merged = u if merged.empty else merged.merge(u, on="date", how="outer")
        merged = merged.sort_values("date").fillna(0)

        if "clicks" in merged.columns:
            hero.add_trace(go.Scatter(
                x=merged["date"], y=rolling_total(merged["clicks"], ROLLING_WINDOW_DAYS),
                mode="lines", name="GSC clicks (28-day total)",
                line=dict(color=BRAND_NAVY, width=2.5),
            ))
        if "users" in merged.columns:
            hero.add_trace(go.Scatter(
                x=merged["date"], y=rolling_total(merged["users"], ROLLING_WINDOW_DAYS),
                mode="lines", name="GA4 organic users (28-day total)",
                line=dict(color=BRAND_GREEN, width=2.5),
            ))
        if show_impr and "impressions" in merged.columns:
            hero.add_trace(go.Scatter(
                x=merged["date"], y=rolling_total(merged["impressions"], ROLLING_WINDOW_DAYS),
                mode="lines", name="Impressions (28-day total, right axis)",
                line=dict(color=BRAND_GRAY, width=1.5, dash="dot"), yaxis="y2",
            ))
        hero_caption = ("Each point = the real total of the trailing 28 days, so the line "
                        "reads at monthly scale and closely tracks true monthly traffic. "
                        "It is a rolling 28-day window, not a calendar month, and begins "
                        "27 days after the range start.")
        if section_active and not hero_split:
            st.info("A section filter is active. Daily GSC clicks by section need query-level "
                    "pulls, so the combined hero still reflects the whole site. Turn on "
                    "'Split hero by section' in the sidebar for section lines (GA4 users), "
                    "or the section table below for per-section clicks.")

    hero.update_layout(
        height=380, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=50, t=20, b=30),
        yaxis=dict(title="28-day total"),
        yaxis2=dict(title="Impressions", overlaying="y", side="right", showgrid=False),
    )
    st.plotly_chart(hero, use_container_width=True)
    st.caption(hero_caption)
    st.divider()

    # ── Row 3: Exact daily trend (granularity + smoothing) ──
    st.subheader(f"Exact trend — {granularity.lower()}")
    daily = go.Figure()

    g_rs = resample_timeseries(g_daily_c, "date", granularity, ["clicks", "impressions"]) \
        if not g_daily_c.empty else pd.DataFrame()
    ga_rs = resample_timeseries(ga_daily_c.rename(columns={"totalUsers": "users"}),
                                "date", granularity, ["users"]) \
        if not ga_daily_c.empty else pd.DataFrame()

    if not g_rs.empty:
        y = apply_smoothing(g_rs["clicks"], smoothing) if granularity == "Daily" else g_rs["clicks"]
        daily.add_trace(go.Scatter(x=g_rs["date"], y=y, mode="lines",
                                   name="GSC clicks", line=dict(color=BRAND_NAVY, width=2)))
    if not ga_rs.empty:
        y = apply_smoothing(ga_rs["users"], smoothing) if granularity == "Daily" else ga_rs["users"]
        daily.add_trace(go.Scatter(x=ga_rs["date"], y=y, mode="lines",
                                   name="GA4 organic users", line=dict(color=BRAND_GREEN, width=2)))
    daily.update_layout(
        height=320, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=20, b=30), yaxis_title="Count",
    )
    st.plotly_chart(daily, use_container_width=True)
    smooth_note = f" · {smoothing.lower()} applied" if (granularity == "Daily" and smoothing != "Raw") else ""
    st.caption(f"Exact {granularity.lower()} values from GSC + GA4{smooth_note}. "
               "This is the precise day-by-day series behind the smoothed hero above.")
    st.divider()

    # ── Row 4: What moved — growth AND decline ──
    if show_cmp and not joined_p.empty:
        st.subheader("What moved")
        gcol, dcol = st.columns(2)

        # pages movers (section-aware, dedup-safe via the fixed join)
        pc = joined_c[["page_path", "section", "users"]].rename(columns={"users": "users_c"})
        pp = joined_p[["page_path", "users"]].rename(columns={"users": "users_p"})
        movers = pc.merge(pp, on="page_path", how="outer")
        movers["section"] = movers["section"].fillna("Main Site")
        movers["users_c"] = _nz(movers["users_c"]).astype(int)
        movers["users_p"] = _nz(movers["users_p"]).astype(int)
        movers["change"] = movers["users_c"] - movers["users_p"]
        movers = movers.drop_duplicates(subset=["page_path"])

        with gcol:
            st.markdown("**Top growing pages**")
            for _, r in movers.nlargest(5, "change").iterrows():
                if r["change"] <= 0:
                    continue
                pct = f" (+{r['change']/r['users_p']*100:.0f}%)" if r["users_p"] else " (new)"
                st.markdown(
                    f'<div style="padding:6px 10px;margin:3px 0;background:#E2EFDA;border-radius:6px;font-size:13px;">'
                    f'<b>{r["page_path"][:64]}</b><br>'
                    f'<span style="color:{BRAND_GREEN};">+{int(r["change"]):,} users{pct}</span>'
                    f' <span style="color:#888;">· {r["section"]}</span></div>',
                    unsafe_allow_html=True)
        with dcol:
            st.markdown("**Top declining pages**")
            for _, r in movers.nsmallest(5, "change").iterrows():
                if r["change"] >= 0:
                    continue
                pct = f" ({r['change']/r['users_p']*100:.0f}%)" if r["users_p"] else ""
                st.markdown(
                    f'<div style="padding:6px 10px;margin:3px 0;background:#FDE7E9;border-radius:6px;font-size:13px;">'
                    f'<b>{r["page_path"][:64]}</b><br>'
                    f'<span style="color:{BRAND_RED};">{int(r["change"]):,} users{pct}</span>'
                    f' <span style="color:#888;">· {r["section"]}</span></div>',
                    unsafe_allow_html=True)
        st.divider()

    # ── Row 5: Section split ──
    st.subheader("By section")
    if not joined_c.empty:
        sec_c = joined_c.groupby("section", as_index=False).agg(
            users_current=("users", "sum"),
            clicks_current=("gsc_clicks", "sum"),
        )
        if show_cmp and not joined_p.empty:
            sec_p = joined_p.groupby("section", as_index=False).agg(users_previous=("users", "sum"))
            sec_t = sec_c.merge(sec_p, on="section", how="left").fillna({"users_previous": 0})
            sec_t["change"] = sec_t["users_current"] - sec_t["users_previous"]
            sec_t["pct_change"] = sec_t.apply(
                lambda r: (r["change"] / r["users_previous"] * 100) if r["users_previous"] else None, axis=1)
        else:
            sec_t = sec_c.copy()
        sec_t = sec_t.sort_values("users_current", ascending=False)

        lcol, rcol = st.columns([3, 2])
        with lcol:
            fig = px.bar(sec_t, x="section", y="users_current", color="section",
                         color_discrete_map=SECTION_COLORS,
                         labels={"users_current": "Users", "section": ""})
            fig.update_layout(showlegend=False, height=330, margin=dict(l=40, r=10, t=10, b=30))
            st.plotly_chart(fig, use_container_width=True)
        with rcol:
            disp = sec_t.rename(columns={
                "section": "Section", "users_current": "Users",
                "clicks_current": "Clicks", "users_previous": "Prev users",
                "change": "Change", "pct_change": "% change"})
            show_cols = [c for c in ["Section", "Users", "Clicks", "Prev users", "Change", "% change"] if c in disp.columns]
            if "Change" in disp.columns:
                sty = disp[show_cols].style.map(
                    lambda v: f"color:{BRAND_GREEN};font-weight:600" if isinstance(v, (int, float)) and v > 0
                    else (f"color:{BRAND_RED};font-weight:600" if isinstance(v, (int, float)) and v < 0 else ""),
                    subset=[c for c in ["Change", "% change"] if c in show_cols])
                if "% change" in show_cols:
                    sty = sty.format({"% change": lambda v: f"{v:+.0f}%" if pd.notna(v) else "—"})
                st.dataframe(sty, use_container_width=True, hide_index=True)
            else:
                st.dataframe(disp[show_cols], use_container_width=True, hide_index=True)

        meta = f"Binaytara SEO Monitor | Section split | {cs} to {ce}"
        xlsx = to_excel_bytes(sec_t, "Section Split", meta)
        st.download_button("⬇ Export section split", data=xlsx,
                           file_name=make_filename("section_split", cs, ce),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.divider()

    # ── Row 6: Geography by country (GA4) ──
    st.subheader("By country (GA4)")
    with st.spinner("Loading country data..."):
        country_c = fetch_country_traffic(cs, ce, organic_only)
        country_p = fetch_country_traffic(ps, pe, organic_only) if show_cmp else pd.DataFrame()

    if country_c.empty:
        st.info("No country data returned for this range.")
    else:
        ctab = country_c.rename(columns={"totalUsers": "users_current"})[["country", "users_current"]]
        if show_cmp and not country_p.empty:
            cp = country_p.rename(columns={"totalUsers": "users_previous"})[["country", "users_previous"]]
            ctab = ctab.merge(cp, on="country", how="left").fillna({"users_previous": 0})
            ctab["change"] = ctab["users_current"] - ctab["users_previous"]
            ctab["pct_change"] = ctab.apply(
                lambda r: (r["change"] / r["users_previous"] * 100) if r["users_previous"] else None, axis=1)
        total_users = ctab["users_current"].sum()
        ctab["share"] = ctab["users_current"] / total_users * 100 if total_users else 0
        ctab = ctab.sort_values("users_current", ascending=False)
        top = ctab.head(15).copy()

        gl, gr = st.columns([2, 3])
        with gl:
            fig = px.bar(top.head(10).sort_values("users_current"),
                         x="users_current", y="country", orientation="h",
                         labels={"users_current": "Users", "country": ""},
                         color_discrete_sequence=[BRAND_NAVY])
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=30))
            st.plotly_chart(fig, use_container_width=True)
        with gr:
            disp = top.rename(columns={
                "country": "Country", "users_current": "Users", "share": "Share %",
                "users_previous": "Prev users", "change": "Change", "pct_change": "% change"})
            cols = [c for c in ["Country", "Users", "Share %", "Prev users", "Change", "% change"] if c in disp.columns]

            def _hl_row(row):
                base = ["background-color:#EEF4FF" if row["Country"] in ("United States", "India") else ""] * len(cols)
                return base
            sty = disp[cols].style.apply(_hl_row, axis=1)
            fmts = {"Share %": "{:.1f}%"}
            if "% change" in cols:
                fmts["% change"] = lambda v: f"{v:+.0f}%" if pd.notna(v) else "—"
                sty = sty.map(lambda v: f"color:{BRAND_GREEN}" if isinstance(v, (int, float)) and v > 0
                              else (f"color:{BRAND_RED}" if isinstance(v, (int, float)) and v < 0 else ""),
                              subset=[c for c in ["Change", "% change"] if c in cols])
            sty = sty.format(fmts)
            st.dataframe(sty, use_container_width=True, hide_index=True)

        meta = f"Binaytara SEO Monitor | Country | {cs} to {ce}"
        xlsx = to_excel_bytes(ctab, "Country", meta)
        st.download_button("⬇ Export country table", data=xlsx,
                           file_name=make_filename("country", cs, ce),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("United States and India are highlighted. GA4 organic users by country; "
                   "share is of the countries shown for this range.")
