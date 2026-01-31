import os
import streamlit as st
from mock_data import DATASET_ID, VERSION_ID, POLICY_PROFILE_ID
from db import init_db

init_db()

st.set_page_config(page_title="FuSa Req Tool", layout="wide")

st.sidebar.title("FuSa Req Tool")
st.sidebar.caption("Granularity normalization + underspec/overspec + complement suggestions")

# 전역 선택값(나중에 dataset/version 선택 UI로 확장)
if "dataset_id" not in st.session_state:
    st.session_state.dataset_id = os.getenv("DATASET_ID", DATASET_ID)
if "version_id" not in st.session_state:
    st.session_state.version_id = os.getenv("VERSION_ID", VERSION_ID)
if "policy_profile_id" not in st.session_state:
    st.session_state.policy_profile_id = os.getenv("POLICY_PROFILE_ID", POLICY_PROFILE_ID)

st.sidebar.text_input("dataset_id", key="dataset_id")
st.sidebar.text_input("version_id", key="version_id")
st.sidebar.text_input("policy_profile_id", key="policy_profile_id")

st.sidebar.divider()
st.sidebar.write("✅ pages/ 폴더의 멀티페이지로 이동하세요.")
st.write("왼쪽 사이드바에서 페이지를 선택하세요.")