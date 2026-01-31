import streamlit as st
st.title("Design View")
st.write("다음 단계에서 아래를 구현하면 ‘설계 연계’가 살아납니다:")
st.markdown("""
- component 단위 readiness/underspec top-k 랭킹
- (안전메커니즘) action_type × component 커버리지 매트릭스
- export: CSV/JSON 보고서
""")