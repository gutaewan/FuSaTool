import streamlit as st
import pandas as pd
import os
import sys

# [핵심] 분리된 로직 임포트
try:
    from granularity.generator import RequirementGenerator, IR_SLOTS
except ImportError:
    st.error("❌ `granularity/generator.py` 파일이 없습니다.")
    st.stop()

st.set_page_config(page_title="Requirements Explorer", layout="wide")

# --- 헬퍼 함수 ---
def normalize_data_to_list(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for key in ["requirements", "data", "items", "reqs"]:
            if key in data and isinstance(data[key], list): return data[key]
        return [data]
    return []

def deep_search(data, target_keys):
    if not isinstance(data, dict): return None
    target_keys_lower = {k.lower() for k in target_keys}
    for k, v in data.items():
        if k.lower() in target_keys_lower and v: return v
    for k, v in data.items():
        if isinstance(v, dict):
            found = deep_search(v, target_keys)
            if found: return found
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    found = deep_search(item, target_keys)
                    if found: return found
    return None

def sanitize_level(val):
    if not isinstance(val, str): return "L1"
    v_upper = val.upper().strip()
    valid_lvls = ["L1", "LEVEL1", "1", "LEVEL 1", "L2", "LEVEL2", "2", "LEVEL 2",
                  "L3", "LEVEL3", "3", "LEVEL 3", "L4", "LEVEL4", "4", "LEVEL 4",
                  "L5", "LEVEL5", "5", "LEVEL 5"]
    for vl in valid_lvls:
        if v_upper == vl:
            if "1" in vl: return "L1"
            if "2" in vl: return "L2"
            if "3" in vl: return "L3"
            if "4" in vl: return "L4"
            if "5" in vl: return "L5"
    return "L1"

def prepare_dataframe(raw_list):
    extracted = []
    for item in raw_list:
        raw_lvl = str(deep_search(item, ["standard_granularity_level", "level"]) or "L1")
        clean_lvl = sanitize_level(raw_lvl)
        
        row = {
            "Select": False,
            "ID": str(deep_search(item, ["id", "req_id"]) or "N/A"),
            "Current_Level": clean_lvl,
            "Target_Level": clean_lvl,
            
            # [Raw Text 확보]
            "Requirement": str(deep_search(item, ["raw_text", "text", "requirement", "description"]) or ""),
            
            "ASIL": str(deep_search(item, ["asil", "safety_level"]) or "-"),
            "FTTI": str(deep_search(item, ["ftti", "fault_tolerant_time"]) or "-"),
            "Safety Goal": str(deep_search(item, ["safety_goal", "sg", "safety_goals"]) or "-"),
            "Safe State": str(deep_search(item, ["safe_state", "safe_states", "state", "ss"]) or "-"),
            "_vehicle": str(item.get("meta", {}).get("vehicle_models", deep_search(item, ["vehicle"]) or "")),
            "_controller": str(item.get("meta", {}).get("component", deep_search(item, ["component"]) or "")),
        }
        for slot in IR_SLOTS:
            row[slot] = deep_search(item, [slot])
        extracted.append(row)
    return pd.DataFrame(extracted)

# --- 메인 UI ---
st.title("📂 Requirements Explorer & Refiner")

# 1. 데이터 로드 및 복구
if 'raw_data' not in st.session_state or st.session_state.raw_data is None:
    st.error("⚠️ 데이터가 로드되지 않았습니다.")
    st.stop()

if 'explorer_df' not in st.session_state or st.session_state.explorer_df is None or st.session_state.explorer_df.empty:
    with st.spinner("데이터 초기화 중..."):
        raw_list = normalize_data_to_list(st.session_state.raw_data)
        st.session_state.explorer_df = prepare_dataframe(raw_list)

df = st.session_state.explorer_df

# 2. 필터링
target_filter = st.session_state.get("explore_target", None)
if target_filter:
    t_v = str(target_filter["Vehicle"])
    t_c = str(target_filter["Controller"])
    st.caption(f"🔍 Filter: {t_v} | {t_c}")
    mask = df.apply(lambda r: (t_v in r["_vehicle"]) and (t_c in r["_controller"]), axis=1)
    df_view = df[mask].copy()
    if st.button("Show All"):
        st.session_state["explore_target"] = None
        st.rerun()
else:
    df_view = df.copy()

# -------------------------------------------------------------------------
# [Top Control] 전체 레벨 일괄 조정
# -------------------------------------------------------------------------
col_top1, col_top2 = st.columns([2, 1])
with col_top1:
    st.write("#### 🎚️ Global Level Adjuster")
    global_target = st.select_slider(
        "전체 목표 레벨 통일",
        options=["L1", "L2", "L3", "L4", "L5"],
        value="L3"
    )

with col_top2:
    st.write("") 
    st.write("")
    if st.button("Apply to All Rows", type="primary", use_container_width=True):
        for idx in df_view.index:
            st.session_state.explorer_df.at[idx, "Target_Level"] = global_target
        st.toast(f"✅ Applied {global_target} to all rows.")
        st.rerun()

# -------------------------------------------------------------------------
# [Main Table] Data Editor
# -------------------------------------------------------------------------
st.divider()
st.markdown(f"### 📋 Requirements List ({len(df_view)} items)")

column_config = {
    "Select": st.column_config.CheckboxColumn("✅", width="small"),
    "ID": st.column_config.TextColumn("ID", width="small", disabled=True),
    "Current_Level": st.column_config.TextColumn("Cur Lv", width="small", disabled=True),
    "Target_Level": st.column_config.SelectboxColumn(
        "Target Lv (Edit)",
        options=["L1", "L2", "L3", "L4", "L5"],
        width="small",
        required=True
    ),
    # [수정] width=600으로 설정하여 픽셀 단위로 강제 확장 (가로 스크롤이 생기더라도 내용 표시 우선)
    "Requirement": st.column_config.TextColumn("Raw Text", width=600, disabled=True),
    "ASIL": st.column_config.TextColumn("ASIL", width="small", disabled=True),
    "FTTI": st.column_config.TextColumn("FTTI", width="small", disabled=True),
    "Safety Goal": st.column_config.TextColumn("Safety Goal", width="medium", disabled=True),
    "Safe State": st.column_config.TextColumn("Safe State", width="medium", disabled=True),
}

cols_to_show = ["Select", "ID", "Current_Level", "Target_Level", "Requirement", "ASIL", "FTTI", "Safety Goal", "Safe State"]
df_display = df_view[cols_to_show].reset_index(drop=True)

edited_df = st.data_editor(
    df_display,
    column_config=column_config,
    use_container_width=True,
    hide_index=True,
    key="req_editor"
)

# [Sync] 변경 사항 반영
if not edited_df.equals(df_display):
    for i, row in edited_df.iterrows():
        matches = st.session_state.explorer_df[st.session_state.explorer_df['ID'] == row['ID']].index
        if len(matches) > 0:
            orig_idx = matches[0]
            st.session_state.explorer_df.at[orig_idx, "Target_Level"] = row["Target_Level"]
            st.session_state.explorer_df.at[orig_idx, "Select"] = row["Select"]

# -------------------------------------------------------------------------
# [Bottom Panel] Dynamic Suggestion (자동 줄바꿈 뷰)
# -------------------------------------------------------------------------
selected_rows_df = edited_df[edited_df["Select"] == True]

if not selected_rows_df.empty:
    selected_row_data = selected_rows_df.iloc[0]
    req_id = selected_row_data["ID"]
    
    orig_row = st.session_state.explorer_df[st.session_state.explorer_df['ID'] == req_id].iloc[0]
    
    st.divider()
    st.subheader("✨ AI Dynamic Suggestion (Korean)")
    
    c1, c2 = st.columns([1, 2])
    
    with c1:
        target_lvl = orig_row["Target_Level"]
        st.info(f"**ID:** {req_id}\n\n**Target:** {target_lvl} (Current: {orig_row['Current_Level']})")
        model_name = st.selectbox("LLM Model", ["llama3", "mistral"], key="llm_sel")
        
        if st.button("Generate Suggestion", type="primary"):
            gen = RequirementGenerator(model_name=model_name)
            with st.spinner("Analyzing Strategy & Generating..."):
                res = gen.generate_suggestion(orig_row, target_lvl, st.session_state.explorer_df)
            st.session_state["last_result"] = res

    with c2:
        st.markdown("**Original Raw Text (Full View):**")
        
        # [핵심] st.info를 사용하여 긴 텍스트가 자동으로 줄바꿈되어 보이게 함
        # 테이블에서 다 못 본 내용은 여기서 편안하게 확인 가능
        st.info(orig_row['Requirement'], icon="📄")
        
        if "last_result" in st.session_state:
            res = st.session_state["last_result"]
            
            if res and res["status"] == "success":
                st.success(f"**Analysis & Suggestion ({target_lvl}):**")
                
                st.markdown(res['suggestion'])
                st.caption(f"ℹ️ {res['message']}")
                
                final_text = st.text_area("Edit Suggestion before Apply:", value=res['suggestion'], height=200)
                
                if st.button("Apply Text"):
                    idx_to_update = st.session_state.explorer_df[st.session_state.explorer_df['ID'] == req_id].index[0]
                    st.session_state.explorer_df.at[idx_to_update, "Requirement"] = final_text
                    st.success("Updated!")
                    st.session_state.explorer_df.at[idx_to_update, "Select"] = False
                    del st.session_state["last_result"]
                    st.rerun()
            
            elif res and res["status"] == "skipped":
                st.warning(res["message"])
            
            elif res:
                st.error(res["message"])

else:
    st.info("👆 목록에서 **체크박스(✅)**를 선택하면, 전체 텍스트 확인 및 AI 분석이 가능합니다.")