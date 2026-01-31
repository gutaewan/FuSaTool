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

# --- 모듈 임포트 ---
try:
    from granularity.classifier import RequirementClassifier, IR_SLOTS
except ImportError as e:
    st.error(f"모듈 오류: {e}")
    st.stop()

st.set_page_config(page_title="Granularity Analysis", layout="wide")

st.title("📊 요구사항 Completeness Heatmap")
st.caption("차종(Vehicle) 및 제어기(Controller)별 IR Slot 결손 현황 분석")

# --- 1. 데이터 로드 ---
if 'raw_data' not in st.session_state or st.session_state.raw_data is None:
    st.warning("⚠️ Main Page에서 파일을 업로드해주세요.")
    st.stop()

raw_data = st.session_state.raw_data
if isinstance(raw_data, dict):
    raw_data = [raw_data]

# --- 2. 분석 실행 (데이터 전처리) ---
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None

# 상단 컨트롤 패널
col_ctrl1, col_ctrl2 = st.columns([3, 1])
with col_ctrl1:
    st.info("데이터가 변경되었거나 최초 실행 시 '분석 실행' 버튼을 눌러주세요.")
with col_ctrl2:
    use_llm = st.toggle("LLM 자동 분류", value=True)
    run_btn = st.button("🚀 분석 실행", use_container_width=True)

if run_btn:
    with st.spinner("요구사항 분석 및 메타데이터 추출 중..."):
        classifier = RequirementClassifier(use_llm=use_llm)
        results = classifier.analyze_list(raw_data)
        st.session_state.analysis_results = results
        st.success("분석 완료!")

# --- 3. 시각화 및 필터링 ---
if st.session_state.analysis_results:
    results = st.session_state.analysis_results
    df = pd.DataFrame(results)

    st.divider()
    
    # [핵심] 3.1 필터링 사이드바 (또는 상단) 구성
    st.subheader("🔍 필터링 및 그룹핑")
    
    # 데이터프레임에 Vehicle/Controller 컬럼이 없는 경우를 대비
    if "Vehicle" not in df.columns: df["Vehicle"] = "Unknown"
    if "Controller" not in df.columns: df["Controller"] = "Common"
    if "ID" not in df.columns: df["ID"] = df.index.astype(str)

    # 필터 UI
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        # 전체 선택 옵션을 위해 multiselect 사용
        all_vehicles = sorted(df["Vehicle"].unique())
        sel_vehicles = st.multiselect("🚗 차종 선택 (Vehicle)", all_vehicles, default=all_vehicles)
    
    with f_col2:
        all_controllers = sorted(df["Controller"].unique())
        sel_controllers = st.multiselect("🎮 제어기 선택 (Controller)", all_controllers, default=all_controllers)

    # 필터 적용
    filtered_df = df[
        (df["Vehicle"].isin(sel_vehicles)) & 
        (df["Controller"].isin(sel_controllers))
    ].copy()

    if filtered_df.empty:
        st.warning("조건에 맞는 요구사항이 없습니다.")
    else:
        # [핵심] 3.2 히트맵 데이터 가공
        # 정렬: 차종 -> 제어기 -> ID 순서로 정렬해야 히트맵에서 그룹핑되어 보임
        filtered_df = filtered_df.sort_values(by=["Vehicle", "Controller", "ID"])
        
        # Y축 라벨 생성: "[차종|제어기] ID" 형태로 만들어 직관성 부여
        filtered_df["Label"] = (
            "[" + filtered_df["Vehicle"] + "|" + filtered_df["Controller"] + "] " + filtered_df["ID"]
        )
        
        # 결측 여부(0/1) 데이터 생성
        heatmap_data = filtered_df[IR_SLOTS].notnull().astype(int)
        heatmap_data.index = filtered_df["Label"] # Y축을 Label로 교체

        # [핵심] 3.3 히트맵 그리기
        # 높이 자동 조절 (데이터가 많으면 길어짐)
        chart_height = max(500, len(filtered_df) * 30) 

        fig = px.imshow(
            heatmap_data,
            labels=dict(x="IR Slot", y="Requirements (Vehicle | Controller)", color="Completeness"),
            x=IR_SLOTS,
            y=heatmap_data.index,
            color_continuous_scale=["#FFD1D1", "#4CAF50"], # Red(Missing) -> Green(Filled)
            height=chart_height,
            aspect="auto"
        )
        
        fig.update_layout(
            margin=dict(l=0, r=0, t=30, b=0),
            coloraxis_showscale=False,
            xaxis_title="IR Slots (Granularity Axes)",
            yaxis_title=""
        )
        
        # 툴팁 정보 강화
        fig.update_traces(
            hovertemplate="<b>%{y}</b><br>Slot: %{x}<br>Filled: %{z}<extra></extra>"
        )

        st.plotly_chart(fig, use_container_width=True)

        # 3.4 통계 요약
        st.caption(f"총 **{len(filtered_df)}**건의 요구사항이 표시되었습니다.")
        
        # 차종별 결손율 보기
        # 6.7 통계 요약 (완성도 차트)
        with st.expander("📊 차종/제어기별 완성도 통계 보기", expanded=True):
            try:
                # 1. 그룹별 전체 슬롯 개수 (분모)
                group_counts = filtered_df.groupby(["Vehicle", "Controller"]).size()
                total_slots = group_counts * len(IR_SLOTS)
                
                # 2. 그룹별 채워진 슬롯 개수 (분자)
                filled_slots = filtered_df.groupby(["Vehicle", "Controller"])[IR_SLOTS].count().sum(axis=1)
                
                # 3. 퍼센트 계산 (Series 형태)
                completeness_series = (filled_slots / total_slots) * 100
                
                # [수정 핵심] 4. MultiIndex를 평평한 DataFrame으로 변환
                # reset_index()를 하면 인덱스가 'Vehicle', 'Controller' 컬럼으로 변합니다.
                chart_df = completeness_series.reset_index(name='Completeness(%)')
                
                # 5. X축 라벨 생성 (차종 + 제어기)
                chart_df['Group'] = chart_df['Vehicle'] + " | " + chart_df['Controller']
                
                # 6. 명시적으로 x, y축 지정하여 차트 그리기
                st.bar_chart(
                    chart_df, 
                    x='Group', 
                    y='Completeness(%)',
                    color='Vehicle' # 차종별로 색상 구분 (선택사항)
                )
                
                # 표로도 데이터 보여주기
                st.dataframe(chart_df[['Vehicle', 'Controller', 'Completeness(%)']], hide_index=True)

            except Exception as e:
                st.error(f"통계 생성 중 오류 발생: {e}")

else:
    st.info("데이터 로드 대기 중...")