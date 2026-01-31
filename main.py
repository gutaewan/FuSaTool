import streamlit as st
import sys
import os
import json

# --- 경로 강제 설정 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --- 페이지 설정 ---
st.set_page_config(
    page_title="Requirements Granularity Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 모듈 임포트 (폴더명 database로 변경) ---
try:
    # fileio는 그대로, sqlite는 database로 변경되었습니다.
    from fileio.parser import parse_json_requirements, save_temp_data
    from database.db_handler import DatabaseHandler  # <--- 여기가 변경됨
except ImportError as e:
    st.error(f"❌ 모듈 임포트 오류: {e}")
    st.info("💡 1. 'sqlite' 폴더 이름을 'database'로 바꿨는지 확인하세요.")
    st.info("💡 2. 'database' 폴더 안에 '__init__.py'가 있는지 확인하세요.")
    st.stop()

# --- 1. 세션 초기화 ---
if 'raw_data' not in st.session_state:
    st.session_state.raw_data = None
if 'file_name' not in st.session_state:
    st.session_state.file_name = None
if 'db_ids' not in st.session_state:
    st.session_state.db_ids = []

# --- 2. 사이드바 ---
with st.sidebar:
    st.header("📂 파일 관리")
    uploaded_file = st.file_uploader("JSON 요구사항 파일 선택", type=['json'], key="main_uploader")

    if st.button("🗑️ 데이터 초기화 (Reset)"):
        st.session_state.raw_data = None
        st.session_state.file_name = None
        st.session_state.db_ids = []
        st.rerun()

# --- 3. 데이터 처리 ---
if uploaded_file is not None and uploaded_file.name != st.session_state.file_name:
    with st.spinner("파일 분석 및 DB 저장 중..."):
        try:
            uploaded_file.seek(0)
            data = parse_json_requirements(uploaded_file)
            
            if data:
                st.session_state.raw_data = data
                st.session_state.file_name = uploaded_file.name
                
                # 임시 파일 저장
                save_temp_data(data, "current_session_data.json")
                
                # DB 저장 (클래스 호출)
                # database/db_handler.py에 DatabaseHandler 클래스가 있어야 함
                db = DatabaseHandler() 
                inserted_ids = db.insert_requirements(uploaded_file.name, data)
                st.session_state.db_ids = inserted_ids
                
                st.success(f"✅ '{uploaded_file.name}' 저장 완료!")
                st.rerun()
        except Exception as e:
            st.error(f"처리 중 오류: {e}")

elif uploaded_file is None and st.session_state.raw_data is not None:
    pass

# --- 4. 메인 화면 출력 ---
st.title("🛡️ 요구사항 관리 시스템")

if st.session_state.raw_data:
    st.info(f"현재 작업 중인 파일: **{st.session_state.file_name}**")
    
    col1, col2, col3 = st.columns(3)
    
    # 데이터 타입에 따라 개수 표시 방식 변경
    data_count = 0
    if isinstance(st.session_state.raw_data, list):
        data_count = len(st.session_state.raw_data)
    elif isinstance(st.session_state.raw_data, dict):
        # 딕셔너리인 경우 키의 개수를 세거나 1로 간주
        data_count = len(st.session_state.raw_data.keys())

    with col1:
        st.metric(label="데이터 항목 수", value=f"{data_count} 개")
    with col2:
        if st.session_state.db_ids:
            range_str = f"{st.session_state.db_ids[0]} ~ {st.session_state.db_ids[-1]}"
        else:
            range_str = "N/A"
        st.metric(label="DB 저장 ID", value=range_str)
    with col3:
        st.metric(label="상태", value="Active ✅")
        
    st.divider()
    st.subheader("데이터 미리보기")
    
    # [수정된 부분] 데이터가 리스트인지 딕셔너리인지 확인하여 출력
    preview_data = {}
    if isinstance(st.session_state.raw_data, list) and len(st.session_state.raw_data) > 0:
        st.caption("형식: 리스트(List) - 첫 번째 항목을 보여줍니다.")
        preview_data = st.session_state.raw_data[0]
    elif isinstance(st.session_state.raw_data, dict):
        st.caption("형식: 객체(Dictionary) - 전체 내용을 보여줍니다.")
        preview_data = st.session_state.raw_data
    else:
        st.warning("데이터가 비어있거나 올바르지 않은 형식입니다.")

    st.json(preview_data)
    
    st.divider()
    st.success("데이터가 로드되었습니다. 왼쪽 사이드바의 **Pages** 메뉴로 이동하여 분석을 시작하세요.")

else:
    st.warning("👈 왼쪽 사이드바에서 JSON 파일을 업로드해 주세요.")
    st.markdown("""
    ### 🚀 시작하기
    1. **Browse files** 버튼을 눌러 JSON 파일을 선택하세요.
    2. 파일이 자동으로 파싱되고 **SQLite DB**에 저장됩니다.
    """)