import streamlit as st
import os
import json

# 모듈 임포트 (파일 구조에 맞게)
try:
    from fileio.parser import parse_json_requirements, save_temp_data
    from sqlite.db_handler import DatabaseHandler
except ImportError:
    # 모듈이 없을 경우를 대비한 안전장치
    st.error("필수 모듈(fileio, sqlite)을 찾을 수 없습니다.")
    st.stop()

st.set_page_config(
    page_title="Requirements Granularity Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 1. 세션 상태(Session State) 초기화 ---
# 페이지가 리로드되어도 이 변수들은 메모리에 계속 남아있습니다.
if 'raw_data' not in st.session_state:
    st.session_state.raw_data = None  # 파싱된 JSON 데이터
if 'file_name' not in st.session_state:
    st.session_state.file_name = None # 현재 로드된 파일명
if 'db_ids' not in st.session_state:
    st.session_state.db_ids = []      # DB에 저장된 ID들 (추후 업데이트용)

# --- 2. 사이드바: 파일 입력 및 초기화 ---
with st.sidebar:
    st.header("📂 파일 관리")
    
    # 파일 업로더
    uploaded_file = st.file_uploader(
        "JSON 요구사항 파일 선택", 
        type=['json'], 
        key="main_uploader"
    )

    # 데이터 초기화 버튼
    if st.button("🗑️ 데이터 초기화 (Reset)"):
        st.session_state.raw_data = None
        st.session_state.file_name = None
        st.session_state.db_ids = []
        st.rerun()

# --- 3. 데이터 처리 로직 (핵심: 세션 유지) ---

# Case A: 새로운 파일이 업로드되었을 때 (기존 파일명과 다를 경우)
if uploaded_file is not None and uploaded_file.name != st.session_state.file_name:
    with st.spinner("파일을 분석하고 DB에 저장 중입니다..."):
        try:
            # 1. 파일 파싱
            uploaded_file.seek(0)
            data = parse_json_requirements(uploaded_file)
            
            if data:
                # 2. 세션에 저장 (메모리 상주)
                st.session_state.raw_data = data
                st.session_state.file_name = uploaded_file.name
                
                # 3. 임시 파일 저장 (물리 파일 백업)
                save_temp_data(data, "current_session_data.json")
                
                # 4. SQLite DB 저장 (영구 저장)
                db = DatabaseHandler()
                inserted_ids = db.insert_requirements(uploaded_file.name, data)
                st.session_state.db_ids = inserted_ids # 저장된 ID 추적
                
                st.success(f"✅ '{uploaded_file.name}' 로드 및 저장 완료!")
                st.rerun() # 화면 갱신
        except Exception as e:
            st.error(f"파일 처리 중 오류 발생: {e}")

# Case B: 업로드된 파일은 없지만, 이미 세션에 데이터가 있는 경우 (페이지 이동 등)
elif uploaded_file is None and st.session_state.raw_data is not None:
    # 아무 작업도 하지 않고 기존 st.session_state.raw_data를 그대로 사용합니다.
    pass

# --- 4. 메인 화면 출력 ---
st.title("🛡️ 요구사항 관리 시스템")

# 데이터가 세션에 존재하면 화면을 표시
if st.session_state.raw_data:
    st.info(f"현재 작업 중인 파일: **{st.session_state.file_name}**")
    
    # 현황판
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="총 요구사항", value=f"{len(st.session_state.raw_data)} 건")
    with col2:
        st.metric(label="DB 저장 ID 범위", value=f"{st.session_state.db_ids[0]} ~ {st.session_state.db_ids[-1]}" if st.session_state.db_ids else "N/A")
    with col3:
        st.metric(label="상태", value="Active ✅")
        
    st.divider()
    
    # 미리보기
    st.subheader("데이터 미리보기")
    st.json(st.session_state.raw_data[0] if st.session_state.raw_data else {})
    
    st.divider()
    st.success("데이터가 로드되었습니다. 왼쪽 사이드바의 **Pages** 메뉴로 이동하여 분석을 시작하세요.")

else:
    # 데이터가 없을 때
    st.warning("👈 왼쪽 사이드바에서 JSON 파일을 업로드해 주세요.")
    st.markdown("""
    ### 🚀 시작하기
    1. **Browse files** 버튼을 눌러 JSON 파일을 선택하세요.
    2. 파일이 자동으로 파싱되고 **SQLite DB**에 저장됩니다.
    3. 이후 **Pages** 메뉴에서 상세 분석을 수행할 수 있습니다.
    """)