# Binaytara SEO Monitor (v2)

Interactive GA4 + Google Search Console organic-traffic monitor for binaytara.org.
Real data only (no third-party estimates): GSC clicks/impressions/CTR/position and
GA4 organic users.

## What's new in v2
- **Global chart controls** (sidebar): date range with independent Period A vs Period B
  comparison, granularity (Daily / Weekly / Monthly), smoothing (Raw / 7-day / 28-day),
  organic vs total, and a section multiselect that drives the dashboard.
- **Overview tab**
  - Run-rate scorecards (clicks, users, impressions, CTR, avg position) with growth
    shown green and decline red; average position uses inverted coloring (down is good).
  - **Monthly-scale hero**: a rolling 28-day total line that reads at monthly magnitude
    and closely tracks true monthly traffic (real data, not an estimate). Optional
    split-by-section overlay and impressions on a second axis.
  - **Exact trend** chart: the precise daily/weekly/monthly series behind the hero.
  - **What moved**: top growing and top declining pages, side by side.
  - Section split (bar + table) and **geography by country** (GA4), US and India highlighted.
- **Search Performance tab** (GSC diagnostic): which lever moved (impressions vs position
  vs CTR), metric trends over time, position-bucket distribution (current vs previous, with
  an optional over-time trend), branded vs non-branded, and device split.
- **Pages / Keyword Deep Dive / Opportunities** carried over; striking-distance band is now
  selectable (default 11–20, the agency standard; 8–20 / 5–20 / 4–15 available).
- **Duplicate-row bug fixed**: the GSC side of the page join is now collapsed to one row per
  normalized path (http/https, trailing slash, case, encoding), so a page can no longer
  appear several times in the gainers/losers lists.

## Accuracy notes built in
- Recent partial days are excluded automatically (GSC finalized data only).
- Average position is impression-weighted (an average across impressions, not a daily rank).
- Query-level clicks exclude GSC-anonymized low-volume queries, so they run slightly under
  the site total (labeled on the tab).

## Deploy
1. Service account with **GA4 Viewer** (property 468739074) and **GSC Full** access
   (sc-domain:binaytara.org). Enable the Google Analytics Data API and Search Console API.
2. Push to GitHub, deploy on Streamlit Community Cloud (https://share.streamlit.io),
   main file `app.py`.
3. Advanced settings → Secrets → paste the service-account JSON as `[gcp_service_account]`
   (see `.streamlit/secrets.toml` template).

Config (property IDs, sections, thresholds, branded terms, striking band) lives in `config.py`.
