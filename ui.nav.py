# ------------------------- Top navigation (horizontal) -------------------------
PAGES = [
    ("Data Import", "pages/0_Data_import.py"),
    ("Overview", "pages/1_Overview.py"),
    ("Requirements Explorer", "pages/2_Requirements_Explorer.py"),
    ("Requirement Detail", "pages/3_Requirement_Detail.py"),
]

def _hide_sidebar_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarNav"] { display: none !important; }
        section.main { padding-left: 1rem !important; }
        .block-container { padding-top: 1.0rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_top_nav(current_path: str, title: str = "") -> None:
    _hide_sidebar_css()

    nav_cols = st.columns([1] * len(PAGES), vertical_alignment="center")
    for i, (name, path) in enumerate(PAGES):
        if nav_cols[i].button(
            name,
            use_container_width=True,
            disabled=(path == current_path),
            key=f"nav_{current_path}_{path}",
        ):
            st.switch_page(path)

    if title:
        st.caption(title)

    st.divider()