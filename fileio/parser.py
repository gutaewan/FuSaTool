import json
import os

def parse_json_requirements(uploaded_file):
    """JSON 파일을 읽어 파이썬 객체로 변환"""
    try:
        content = uploaded_file.read()
        data = json.loads(content)
        return data
    except Exception as e:
        print(f"Parsing Error: {e}")
        return None

def save_temp_data(data, filename):
    """임시 데이터를 fileio 폴더 내에 저장"""
    target_dir = "fileio/temp"
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    
    path = os.path.join(target_dir, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)