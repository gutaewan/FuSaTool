import streamlit as st
from api_client import USE_MOCK
from mock_data import mock_list_requirements

st.title("Requirements Explorer")

dataset_id = st.session_state.get("dataset_id", "ds_001")
version_id = st.session_state.get("version_id", "v_001")

colA, colB = st.columns([3,2])
search = colA.text_input("Search", "")
sort = colB.selectbox("Sort", ["underspec_desc","overspec_desc"], index=0)

if USE_MOCK:
    data = mock_list_requirements(search, sort)
else:
    from api_client import list_requirements
    data = list_requirements(dataset_id, version_id, search=search, sort=sort)


items = data.get("items", [])
total = data.get("total", len(items))
st.caption(f"Total: {total}")

# ---- Lightweight table renderer (no pyarrow/pandas) ----
show_cols = [
    "req_id",
    "source",
    "domain",
    "component",
    "goal",
    "action_type",
    "underspec",
    "overspec",
    "unknown_count",
]

page_size = st.selectbox("Rows per page", [10, 20, 50, 100], index=1)
max_page = max(1, (len(items) + page_size - 1) // page_size)
page = st.number_input("Page", min_value=1, max_value=max_page, value=1, step=1)
start = (page - 1) * page_size
end = start + page_size
page_items = items[start:end]

# Header
header_cols = st.columns([2, 1, 1, 1, 1, 1, 1, 1, 1])
for c, k in zip(header_cols, show_cols):
    c.markdown(f"**{k}**")

# Rows
for row in page_items:
    cols = st.columns([2, 1, 1, 1, 1, 1, 1, 1, 1])
    for c, k in zip(cols, show_cols):
        v = row.get(k, "")
        c.write(v)

st.divider()
st.subheader("Open detail")

options = [x.get("req_id", "") for x in page_items if x.get("req_id")]
if not options and items:
    options = [x.get("req_id", "") for x in items[:50] if x.get("req_id")]

selected = st.selectbox("Select req_id", options=options, index=0 if options else None)
if st.button("Go to Requirement Detail", disabled=(not bool(selected))):
    st.session_state.selected_req_id = selected
    st.switch_page("pages/3_Requirement_Detail.py")