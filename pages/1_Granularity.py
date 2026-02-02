import streamlit as st
import sys
import os
import pandas as pd
import plotly.express as px

# --- 경로 설정 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from granularity.classifier import RequirementClassifier, IR_SLOTS
except ImportError as e:
    st.error(f"모듈 로드 실패: {e}")
    st.stop()

st.set_page_config(page_title="Granularity Analysis", layout="wide")
st.title("📊 Granularity Level Heatmap")

# --- 데이터 정규화 ---
def normalize_data_to_list(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for key in ["requirements", "data", "items", "reqs"]:
            if key in data and isinstance(data[key], list): return data[key]
        return [data]
    return []

# --- 1. 데이터 로드 ---
if 'raw_data' not in st.session_state or st.session_state.raw_data is None:
    st.warning("⚠️ Main Page에서 파일을 업로드해주세요.")
    st.stop()

processed_data_list = normalize_data_to_list(st.session_state.raw_data)

# --- 2. 분석 실행 (세션 유지) ---
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None

col_c1, col_c2 = st.columns([3, 1])
with col_c1:
    if st.session_state.analysis_results is not None:
        st.success(f"✅ 분석된 데이터가 로드되었습니다. ({len(st.session_state.analysis_results)}건)")
    else:
        st.info(f"✅ 분석 대상: {len(processed_data_list)}건")

with col_c2:
    use_llm = st.toggle("LLM 자동 분류", value=False)
    if st.button("🚀 분석 실행", type="primary"):
        with st.spinner("분석 중..."):
            try:
                classifier = RequirementClassifier(use_llm=use_llm)
                results = classifier.analyze_list(processed_data_list)
                if results:
                    st.session_state.analysis_results = results
                    st.success("완료!")
                    st.rerun()
                else:
                    st.error("결과 없음")
            except Exception as e:
                st.error(f"Error: {e}")

# --- 3. 히트맵 및 수동 선택 ---
if st.session_state.analysis_results:
    df = pd.DataFrame(st.session_state.analysis_results)
    st.divider()

    # 레벨 매핑
    def map_level_to_score(level_str):
        if not isinstance(level_str, str): return 0
        s = level_str.upper().strip()
        if s in ["L1", "LEVEL1", "1"]: return 1
        if s in ["L2", "LEVEL2", "2"]: return 2
        if s in ["L3", "LEVEL3", "3"]: return 3
        if s in ["L4", "LEVEL4", "4"]: return 4
        if s in ["L5", "LEVEL5", "5"]: return 5
        return 0

    if "Level" not in df.columns: df["Level"] = "Unknown"
    df['Level_Num'] = df['Level'].apply(map_level_to_score)

    # 필터 데이터 준비
    def get_unique(series):
        s = set()
        for x in series:
            if isinstance(x, list): s.update(str(i) for i in x)
            else: s.add(str(x))
        return sorted(list(s))

    all_controllers = get_unique(df["Controller"])
    
    # ------------------------------------------------------------------
    # [히트맵 그리기]
    # ------------------------------------------------------------------
    try:
        # 히트맵 데이터 준비
        df_exp = df.explode('Vehicle').explode('Controller')
        df_exp['Vehicle'] = df_exp['Vehicle'].astype(str)
        df_exp['Controller'] = df_exp['Controller'].astype(str)
        
        matrix = df_exp.pivot_table(index='Controller', columns='Vehicle', values='Level_Num', aggfunc='mean').fillna(0)
        
        fig = px.imshow(
            matrix,
            labels=dict(x="차종", y="제어기", color="Avg Level"),
            text_auto=".1f",
            aspect="auto",
            color_continuous_scale="Viridis",
            zmin=0, zmax=5
        )
        fig.update_layout(height=max(500, len(matrix.index)*40), xaxis_side="top")
        
        # Native Click Event
        event = st.plotly_chart(fig, on_select="rerun", selection_mode="points", key="heatmap_obj")
        
        # 클릭 시 이동 로직
        if event and len(event.selection.points) > 0:
            point = event.selection.points[0]
            try:
                st.session_state["explore_target"] = {"Vehicle": point.x, "Controller": point.y}
                st.switch_page("pages/2_Requirements_Explorer.py")
            except: pass

    except Exception as e:
        st.warning("히트맵 생성 중 오류가 발생했습니다. 아래 수동 선택 기능을 이용해주세요.")

    # ------------------------------------------------------------------
    # [확실한 해결책] 수동 선택 패널 (Fallback UI)
    # ------------------------------------------------------------------
    st.divider()
    st.markdown("### 🎯 분석 결과 탐색 (수동 선택)")
    st.caption("히트맵 클릭이 안 되거나, 특정 제어기를 직접 찾고 싶을 때 사용하세요.")

    col_man1, col_man2, col_man3 = st.columns([1, 1, 1])
    
    with col_man1:
        # 1. 제어기 선택
        selected_ctrl = st.selectbox("1. 제어기 선택 (Controller)", all_controllers)

    with col_man2:
        # 2. 해당 제어기에 존재하는 차종만 필터링하여 표시
        # 선택된 제어기를 포함하는 행들 찾기
        mask_c = df["Controller"].apply(lambda x: selected_ctrl in (x if isinstance(x, list) else [x]))
        filtered_by_c = df[mask_c]
        available_vehicles = get_unique(filtered_by_c["Vehicle"])
        
        selected_vh = st.selectbox("2. 차종 선택 (Vehicle)", available_vehicles)

    with col_man3:
        st.write("") # 간격 맞춤용
        st.write("") 
        # 3. 이동 버튼
        if st.button("👉 상세 탐색기로 이동", type="primary", use_container_width=True):
            st.session_state["explore_target"] = {
                "Vehicle": selected_vh,
                "Controller": selected_ctrl
            }
            st.switch_page("pages/2_Requirements_Explorer.py")

else:
    st.info("☝️ 상단의 '분석 실행' 버튼을 눌러주세요.")