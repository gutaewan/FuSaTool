import streamlit as st

st.title("Granularity 분석")

# main.py에서 로드된 데이터가 있는지 확인
if 'raw_data' not in st.session_state or st.session_state.raw_data is None:
    st.error("먼저 메인 페이지에서 파일을 업로드해 주세요!")
    st.stop()

# 세션 데이터 사용
data = st.session_state.raw_data
st.write(f"가져온 데이터 샘플 (총 {len(data)}건):")
st.json(data[0]) # 첫 번째 요구사항 표시

# 이후 여기서 IR Slot 분류 및 L1~L5 로직 수행...