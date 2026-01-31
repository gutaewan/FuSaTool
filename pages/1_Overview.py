import os
import streamlit as st
#import pandas as pd
from api_client import USE_MOCK
from mock_data import mock_readiness_cards

st.title("Overview")

dataset_id = st.session_state.get("dataset_id", "ds_001")
version_id = st.session_state.get("version_id", "v_001")

if "dataset_id" not in st.session_state or "version_id" not in st.session_state:
    st.caption("(note) dataset_id/version_id not set in session_state; using defaults.")

if USE_MOCK:
    cards = mock_readiness_cards()
else:
    from api_client import get_readiness_cards
    cards = get_readiness_cards(dataset_id, version_id)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Verification readiness", f"{cards['verification']*100:.0f}%")
c2.metric("Acceptance readiness", f"{cards['acceptance']*100:.0f}%")
c3.metric("Constraints readiness", f"{cards['constraints']*100:.0f}%")
c4.metric("Evidence", f"{cards['evidence']*100:.0f}%")

st.divider()
st.subheader("Next")
st.write("- Heatmap(component×slot), Scatter(underspec×overspec)는 다음 단계에서 차트로 붙이세요.")