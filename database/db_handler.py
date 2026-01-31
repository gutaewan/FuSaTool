import sqlite3
import json
import os
from datetime import datetime

class DatabaseHandler:
    def __init__(self, db_path="database/requirements.db"):
        """
        데이터베이스 핸들러 초기화
        :param db_path: DB 파일 경로 (기본값: database 폴더 내 requirements.db)
        """
        # DB 파일이 저장될 폴더가 없으면 생성
        directory = os.path.dirname(db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        """SQLite DB 연결 객체 반환"""
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """테이블 초기화 (없으면 생성)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 1. 요구사항 원문 테이블
        # source_file: 업로드한 파일명
        # original_text: JSON 객체 전체를 문자열로 저장
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                original_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. 분석 결과 테이블 (Granularity 및 IR Slots)
        # 1:1 또는 1:N 관계 설정을 위해 req_id를 외래키로 사용
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                req_id INTEGER,
                why TEXT,
                what TEXT,
                how_type TEXT,
                when_condition TEXT,
                constraints TEXT,
                verification TEXT,
                acceptance TEXT,
                anchors TEXT,
                goal TEXT,
                missing_parts TEXT,  -- JSON String (결손부 리스트)
                excess_parts TEXT,   -- JSON String (과잉부 리스트)
                granularity_level TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(req_id) REFERENCES requirements(id)
            )
        ''')
        
        conn.commit()
        conn.close()

    def insert_requirements(self, filename, requirements_list):
        """
        대량의 요구사항 원문을 저장합니다.
        :param filename: 소스 파일명
        :param requirements_list: 요구사항 리스트 (Dict 또는 String)
        :return: 저장된 행의 ID 리스트
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        inserted_ids = []
        try:
            for req in requirements_list:
                # req가 딕셔너리(JSON 객체)라면 문자열로 변환, 이미 문자열이면 그대로 사용
                text_content = json.dumps(req, ensure_ascii=False) if isinstance(req, dict) else str(req)
                
                cursor.execute('''
                    INSERT INTO requirements (source_file, original_text)
                    VALUES (?, ?)
                ''', (filename, text_content))
                inserted_ids.append(cursor.lastrowid)
            
            conn.commit()
        except Exception as e:
            print(f"DB Insert Error: {e}")
            conn.rollback()
        finally:
            conn.close()
            
        return inserted_ids

    def save_analysis_result(self, req_id, analysis_data):
        """
        특정 요구사항(req_id)에 대한 분석 결과를 저장합니다.
        :param req_id: requirements 테이블의 ID
        :param analysis_data: 분석 결과 딕셔너리
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # 리스트 형태의 데이터는 JSON 문자열로 변환하여 저장
            missing = json.dumps(analysis_data.get('missing_parts', []), ensure_ascii=False)
            excess = json.dumps(analysis_data.get('excess_parts', []), ensure_ascii=False)

            cursor.execute('''
                INSERT INTO analysis_results (
                    req_id, why, what, how_type, when_condition, 
                    constraints, verification, acceptance, anchors, goal,
                    missing_parts, excess_parts, granularity_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                req_id,
                analysis_data.get('Why', ''),
                analysis_data.get('What', ''),
                analysis_data.get('How type', ''),
                analysis_data.get('When', ''),
                analysis_data.get('Constraints', ''),
                analysis_data.get('Verification', ''),
                analysis_data.get('Acceptance criteria', ''),
                analysis_data.get('Anchors', ''),
                analysis_data.get('Goal', ''),
                missing,
                excess,
                analysis_data.get('level', 'L1')
            ))
            conn.commit()
        except Exception as e:
            print(f"DB Analysis Save Error: {e}")
            conn.rollback()
        finally:
            conn.close()

    def fetch_all_requirements(self):
        """저장된 모든 요구사항 원문을 최신순으로 가져옵니다."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, source_file, original_text, created_at FROM requirements ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        # 튜플 리스트를 딕셔너리 리스트로 변환하여 반환
        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "source_file": row[1],
                "original_text": json.loads(row[2]), # JSON 문자열을 다시 객체로 복원
                "created_at": row[3]
            })
        return result

    def get_analysis_by_req_id(self, req_id):
        """특정 요구사항 ID에 대한 분석 결과를 가져옵니다."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM analysis_results WHERE req_id = ? ORDER BY created_at DESC LIMIT 1", (req_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # 컬럼 순서대로 매핑 (이 부분은 필요 시 더 정교하게 수정 가능)
            return {
                "id": row[0],
                "req_id": row[1],
                "Why": row[2],
                "What": row[3],
                "How type": row[4],
                "When": row[5],
                "Constraints": row[6],
                "Verification": row[7],
                "Acceptance criteria": row[8],
                "Anchors": row[9],
                "Goal": row[10],
                "missing_parts": json.loads(row[11]) if row[11] else [],
                "excess_parts": json.loads(row[12]) if row[12] else [],
                "level": row[13]
            }
        return None