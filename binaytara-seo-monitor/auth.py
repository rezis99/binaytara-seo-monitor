"""
Binaytara SEO Monitor — Authentication
Service-account credentials shared by GA4 and GSC clients.
"""

import streamlit as st
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]


@st.cache_resource(show_spinner=False)
def _credentials():
    """Build credentials once per app lifecycle."""
    info = dict(st.secrets["gcp_service_account"])
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


@st.cache_resource(show_spinner=False)
def ga4_client() -> BetaAnalyticsDataClient:
    """Return a GA4 Data API client."""
    return BetaAnalyticsDataClient(credentials=_credentials())


@st.cache_resource(show_spinner=False)
def gsc_service():
    """Return a GSC Search Analytics service."""
    return build("searchconsole", "v1", credentials=_credentials(), cache_discovery=False)
