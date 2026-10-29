"""
Binaytara SEO Monitor — Tab: Search Performance
GSC diagnostic core: which lever moved (impressions vs position vs CTR),
metric trends over time, branded vs non-branded, position-bucket distribution,
and device split.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from config import BRAND_NAVY, BRAND_GREEN, BRAND_RED, BRAND_GRAY
from data.processing import (
    is_branded, position_bucket, bucket_order, resample_timeseries,
)
from export import to_excel_bytes, make_filename


def _wmean(df, col, weight):
    w = df[weight].sum()
    return (df[col] * df[weight]).sum() / w if w else None


def _totals(df):
    if df is None or df.empty:
        return {"clicks": 0, "impr": 0, "ctr": 0, "pos": None}
    clicks = df["clicks"].sum()
    impr = df["impressions"].sum()
    return {
        "clicks": int(clicks), "impr": int(impr),
        "ctr": (clicks / impr) if impr else 0,
        "pos": _wmean(df, "position", "impressions"),
    }


def render(dates, organic_only, section_filter, controls=None):
    from data.gsc import (
        fetch_gsc_daily_totals, fetch_gsc_query_totals,
        fetch_gsc_device_totals, fetch_gsc_date_query,
    )

    controls = controls or {}
    granularity = controls.get("granularity", "Daily")

    cs, ce = dates["curr_start"], dates["curr_end"]
    ps, pe = dates["prev_start"], dates["prev_end"]
    show_cmp = dates.get("show_comparison", True)

    if section_filter and "All Sections" not in section_filter:
        st.info("Search Performance is site-wide (query-level data has no section in GSC). "
                "The section filter applies to the Overview and Pages tabs.")

    with st.spinner("Loading search performance data..."):
        daily_c = fetch_gsc_daily_totals(cs, ce)
        q_c = fetch_gsc_query_totals(cs, ce)
        q_p = fetch_gsc_query_totals(ps, pe) if show_cmp else pd.DataFrame()
        dev_c = fetch_gsc_device_totals(cs, ce)
        dev_p = fetch_gsc_device_totals(ps, pe) if show_cmp else pd.DataFrame()

    if daily_c.empty:
        st.warning("No GSC data for this range.")
        return

    cur = _totals(daily_c.rename(columns={}))
    cur = {"clicks": int(daily_c["clicks"].sum()), "impr": int(daily_c["impressions"].sum())}
    cur["ctr"] = (cur["clicks"] / cur["impr"]) if cur["impr"] else 0
    cur["pos"] = _wmean(daily_c, "position", "impressions")

    if show_cmp:
        daily_p = fetch_gsc_daily_totals(ps, pe)
        prev = {"clicks": int(daily_p["clicks"].sum()), "impr": int(daily_p["impressions"].sum())} if not daily_p.empty else None
        if prev:
            prev["ctr"] = (prev["clicks"] / prev["impr"]) if prev["impr"] else 0
            prev["pos"] = _wmean(daily_p, "position", "impressions")
    else:
        prev = None

    # ── Scorecards ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        d = (cur["clicks"] - prev["clicks"]) if prev else None
        st.metric("Clicks", f"{cur['clicks']:,}", delta=f"{d:+,}" if d is not None else None)
    with c2:
        d = (cur["impr"] - prev["impr"]) if prev else None
        st.metric("Impressions", f"{cur['impr']:,}", delta=f"{d:+,}" if d is not None else None)
    with c3:
        if prev:
            st.metric("CTR", f"{cur['ctr']*100:.2f}%", delta=f"{(cur['ctr']-prev['ctr'])*100:+.2f} pts")
        else:
            st.metric("CTR", f"{cur['ctr']*100:.2f}%")
    with c4:
        if cur["pos"] is not None:
            if prev and prev["pos"] is not None:
                st.metric("Avg position", f"{cur['pos']:.1f}",
                          delta=f"{cur['pos']-prev['pos']:+.1f}", delta_color="inverse")
            else:
                st.metric("Avg position", f"{cur['pos']:.1f}")
        else:
            st.metric("Avg position", "—")

    # ── Lever decomposition ──
    if show_cmp and prev:
        st.markdown("**Which lever moved?**")
        def pct(c, p):
            return ((c - p) / p * 100) if p else None
        rows = [
            ("Clicks", cur["clicks"], prev["clicks"], pct(cur["clicks"], prev["clicks"]), False),
            ("Impressions", cur["impr"], prev["impr"], pct(cur["impr"], prev["impr"]), False),
            ("CTR", cur["ctr"] * 100, prev["ctr"] * 100, pct(cur["ctr"], prev["ctr"]), False),
            ("Avg position", cur["pos"], prev["pos"],
             pct(cur["pos"], prev["pos"]) if (cur["pos"] and prev["pos"]) else None, True),
        ]
        lev = pd.DataFrame(rows, columns=["Metric", "Current", "Previous", "% change", "_lower_better"])
        # readout sentence
        drivers = [r for r in rows if r[3] is not None and r[0] in ("Impressions", "CTR", "Avg position")]
        if drivers:
            biggest = max(drivers, key=lambda r: abs(r[3]))
            name = biggest[0]
            direction = "up" if biggest[3] > 0 else "down"
            if name == "Avg position":
                better = "improved" if biggest[3] < 0 else "worsened"
                sentence = f"Clicks moved mostly with **average position** ({better} by {abs(biggest[3]):.0f}%)."
            else:
                sentence = f"Clicks moved mostly with **{name.lower()}** ({direction} {abs(biggest[3]):.0f}%)."
            st.caption(sentence + " Impressions = demand/visibility; position = ranking; CTR = how "
                       "compelling the result is. This points at which fix matters most.")

        disp = lev.drop(columns=["_lower_better"]).copy()
        def _fmt_row(r):
            if r["Metric"] in ("CTR",):
                return f"{r['Current']:.2f}%", f"{r['Previous']:.2f}%"
            if r["Metric"] == "Avg position":
                return (f"{r['Current']:.1f}" if pd.notna(r['Current']) else "—",
                        f"{r['Previous']:.1f}" if pd.notna(r['Previous']) else "—")
            return f"{r['Current']:,.0f}", f"{r['Previous']:,.0f}"
        disp[["Current", "Previous"]] = [list(_fmt_row(r)) for _, r in lev.iterrows()]
        def _pct_color(row):
            v = lev.loc[row.name, "% change"]
            lower_better = lev.loc[row.name, "_lower_better"]
            if v is None or pd.isna(v):
                return [""] * len(row)
            good = (v < 0) if lower_better else (v > 0)
            color = BRAND_GREEN if good else BRAND_RED
            return ["" if c != "% change" else f"color:{color};font-weight:600" for c in row.index]
        disp["% change"] = disp["% change"].apply(lambda v: f"{v:+.0f}%" if pd.notna(v) else "—")
        st.dataframe(disp.style.apply(_pct_color, axis=1), use_container_width=True, hide_index=True)
    st.divider()

    # ── Metric trends over time ──
    st.subheader(f"Trends over time — {granularity.lower()}")
    rs = resample_timeseries(daily_c, "date", granularity,
                             sum_cols=["clicks", "impressions"],
                             weighted_mean_cols=["ctr", "position"], weight_col="impressions")
    tab_a, tab_b, tab_c = st.tabs(["Clicks & impressions", "CTR", "Average position"])
    with tab_a:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=rs["date"], y=rs["clicks"], name="Clicks",
                                 line=dict(color=BRAND_NAVY, width=2)))
        fig.add_trace(go.Scatter(x=rs["date"], y=rs["impressions"], name="Impressions",
                                 line=dict(color=BRAND_GRAY, width=1.5, dash="dot"), yaxis="y2"))
        fig.update_layout(height=340, hovermode="x unified",
                          yaxis=dict(title="Clicks"),
                          yaxis2=dict(title="Impressions", overlaying="y", side="right", showgrid=False),
                          legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
                          margin=dict(l=40, r=50, t=20, b=30))
        st.plotly_chart(fig, use_container_width=True)
    with tab_b:
        fig = px.line(rs, x="date", y="ctr", labels={"ctr": "CTR"})
        fig.update_traces(line=dict(color=BRAND_GREEN, width=2))
        fig.update_yaxes(tickformat=".1%")
        fig.update_layout(height=320, margin=dict(l=40, r=20, t=20, b=30))
        st.plotly_chart(fig, use_container_width=True)
    with tab_c:
        fig = px.line(rs, x="date", y="position", labels={"position": "Avg position"})
        fig.update_traces(line=dict(color=BRAND_NAVY, width=2))
        fig.update_yaxes(autorange="reversed")  # position 1 at top
        fig.update_layout(height=320, margin=dict(l=40, r=20, t=20, b=30))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Lower is better, so the axis is inverted (position 1 at the top).")
    st.divider()

    # ── Position-bucket distribution (A vs B snapshot) ──
    st.subheader("Position buckets")
    if not q_c.empty:
        def bucket_counts(df, label):
            d = df.copy()
            d["bucket"] = d["position"].apply(position_bucket)
            out = d.groupby("bucket").size().reindex(bucket_order(), fill_value=0)
            return out.rename(label)
        cur_b = bucket_counts(q_c, "Current")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=cur_b.index, y=cur_b.values, name="Current", marker_color=BRAND_NAVY))
        if show_cmp and not q_p.empty:
            prev_b = bucket_counts(q_p, "Previous")
            fig.add_trace(go.Bar(x=prev_b.index, y=prev_b.values, name="Previous", marker_color=BRAND_GRAY))
        fig.update_layout(barmode="group", height=330,
                          legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
                          margin=dict(l=40, r=20, t=20, b=30), yaxis_title="Queries")
        st.plotly_chart(fig, use_container_width=True)

        if show_cmp and not q_p.empty:
            top3_delta = int(cur_b.get("1–3 (Top 3)", 0) - prev_b.get("1–3 (Top 3)", 0))
            p1_delta = int((cur_b.get("1–3 (Top 3)", 0) + cur_b.get("4–10 (Page 1)", 0))
                           - (prev_b.get("1–3 (Top 3)", 0) + prev_b.get("4–10 (Page 1)", 0)))
            color3 = BRAND_GREEN if top3_delta >= 0 else BRAND_RED
            color1 = BRAND_GREEN if p1_delta >= 0 else BRAND_RED
            st.markdown(
                f"<span style='color:{color3};font-weight:600;'>Top-3 queries: {top3_delta:+,}</span> &nbsp;·&nbsp; "
                f"<span style='color:{color1};font-weight:600;'>Page-1 queries (top 10): {p1_delta:+,}</span> "
                "vs the previous period.", unsafe_allow_html=True)
        st.caption("Counts of queries whose impression-weighted average position falls in each band. "
                   "Position is an average, so treat a query's band as a shortlist to check, not an exact rank. "
                   "GSC hides very low-volume (anonymized) queries, so counts are of queries GSC reports.")

        with st.expander("Load position-bucket trend over time (slower — pulls daily query data)"):
            if st.button("Load bucket trend", key="load_bucket_trend"):
                with st.spinner("Pulling daily query data (this can take a moment)..."):
                    dq = fetch_gsc_date_query(cs, ce)
                if dq.empty:
                    st.info("No daily query data returned.")
                else:
                    dq["bucket"] = dq["position"].apply(position_bucket)
                    trend = (dq.groupby(["date", "bucket"]).size().reset_index(name="queries"))
                    trend = resample_timeseries(
                        trend.pivot_table(index="date", columns="bucket", values="queries", aggfunc="sum")
                        .fillna(0).reset_index(),
                        "date", granularity, sum_cols=[b for b in bucket_order() if b in trend["bucket"].unique()])
                    melt = trend.melt(id_vars="date", var_name="bucket", value_name="queries")
                    fig2 = px.area(melt, x="date", y="queries", color="bucket",
                                   category_orders={"bucket": bucket_order()})
                    fig2.update_layout(height=340, margin=dict(l=40, r=20, t=20, b=30))
                    st.plotly_chart(fig2, use_container_width=True)
    st.divider()

    # ── Branded vs non-branded (A vs B snapshot) ──
    st.subheader("Branded vs non-branded")
    if not q_c.empty:
        def brand_split(df):
            d = df.copy()
            d["group"] = d["query"].apply(lambda q: "Branded" if is_branded(q) else "Non-branded")
            return d.groupby("group", as_index=False).agg(clicks=("clicks", "sum"),
                                                          impressions=("impressions", "sum"))
        bc = brand_split(q_c)
        rows = []
        for grp in ["Branded", "Non-branded"]:
            c_clicks = int(bc.loc[bc["group"] == grp, "clicks"].sum())
            row = {"Group": grp, "Clicks": c_clicks}
            if show_cmp and not q_p.empty:
                bp = brand_split(q_p)
                p_clicks = int(bp.loc[bp["group"] == grp, "clicks"].sum())
                row["Prev clicks"] = p_clicks
                row["Change"] = c_clicks - p_clicks
                row["% change"] = (row["Change"] / p_clicks * 100) if p_clicks else None
            rows.append(row)
        bdf = pd.DataFrame(rows)
        total = bdf["Clicks"].sum()
        bdf["Share %"] = bdf["Clicks"] / total * 100 if total else 0

        lc, rc = st.columns([2, 3])
        with lc:
            fig = px.pie(bdf, values="Clicks", names="Group", hole=0.5,
                         color="Group",
                         color_discrete_map={"Branded": BRAND_NAVY, "Non-branded": BRAND_GREEN})
            fig.update_traces(textinfo="label+percent")
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with rc:
            cols = [c for c in ["Group", "Clicks", "Share %", "Prev clicks", "Change", "% change"] if c in bdf.columns]
            sty = bdf[cols].style.format({"Share %": "{:.1f}%",
                                          "% change": lambda v: f"{v:+.0f}%" if pd.notna(v) else "—"})
            if "Change" in cols:
                sty = sty.map(lambda v: f"color:{BRAND_GREEN};font-weight:600" if isinstance(v, (int, float)) and v > 0
                              else (f"color:{BRAND_RED};font-weight:600" if isinstance(v, (int, float)) and v < 0 else ""),
                              subset=[c for c in ["Change", "% change"] if c in cols])
            st.dataframe(sty, use_container_width=True, hide_index=True)
        st.caption("Branded = queries containing Binaytara, OncoBlast, IJCCD, The Cancer News, etc. "
                   "Non-branded growth is the clearest sign of new reach. Query-level clicks exclude "
                   "GSC-anonymized low-volume queries, so they run a little under the site total.")
    st.divider()

    # ── Device split ──
    st.subheader("By device")
    if not dev_c.empty:
        d = dev_c.rename(columns={"clicks": "Clicks", "impressions": "Impressions",
                                  "device": "Device"})[["Device", "Clicks", "Impressions"]]
        if show_cmp and not dev_p.empty:
            dp = dev_p.rename(columns={"clicks": "Prev clicks", "device": "Device"})[["Device", "Prev clicks"]]
            d = d.merge(dp, on="Device", how="left").fillna({"Prev clicks": 0})
            d["Change"] = d["Clicks"] - d["Prev clicks"]
        d = d.sort_values("Clicks", ascending=False)
        dl, dr = st.columns([2, 3])
        with dl:
            fig = px.bar(d, x="Device", y="Clicks", color="Device",
                         color_discrete_sequence=[BRAND_NAVY, BRAND_GREEN, BRAND_GRAY])
            fig.update_layout(showlegend=False, height=280, margin=dict(l=40, r=10, t=10, b=30))
            st.plotly_chart(fig, use_container_width=True)
        with dr:
            if "Change" in d.columns:
                sty = d.style.map(lambda v: f"color:{BRAND_GREEN};font-weight:600" if isinstance(v, (int, float)) and v > 0
                                  else (f"color:{BRAND_RED};font-weight:600" if isinstance(v, (int, float)) and v < 0 else ""),
                                  subset=["Change"])
                st.dataframe(sty, use_container_width=True, hide_index=True)
            else:
                st.dataframe(d, use_container_width=True, hide_index=True)

        meta = f"Binaytara SEO Monitor | Search performance | {cs} to {ce}"
        xlsx = to_excel_bytes(rs, "Trends", meta)
        st.download_button("⬇ Export trend data", data=xlsx,
                           file_name=make_filename("search_performance_trend", cs, ce),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.caption("GSC verification: Search Console → Performance → Search results → compare date ranges; "
               "toggle Queries / Devices / Search appearance to match these panels.")
