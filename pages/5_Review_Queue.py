import streamlit as st
st.title("Review Queue")
st.write("다음 단계에서 아래 기능을 붙이세요:")
st.markdown("""
- UNKNOWN/CONFLICTED 슬롯 중심의 리뷰 카드 큐
- 승인(Confirm) / 보류(Keep Unknown) / 충돌 해결(Resolve Conflict)
- 승인 근거(anchors) 필수화 + 감사 로그
""")