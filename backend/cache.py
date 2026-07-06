import os
import sqlite3
import json

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cache.db"))

class SearchCache:
    def __init__(self):
        self._init_db()
        
    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                node_type TEXT,
                query_key TEXT,
                response_json TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (node_type, query_key)
            )
        """)
        conn.commit()
        conn.close()
        
    def get_cached_result(self, node_type, query_key):
        if not query_key:
            return None
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT response_json FROM cache 
            WHERE node_type = ? AND query_key = ?
        """, (node_type, str(query_key)))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                return None
        return None
        
    def set_cached_result(self, node_type, query_key, result_dict):
        if not query_key or result_dict is None:
            return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO cache (node_type, query_key, response_json)
                VALUES (?, ?, ?)
            """, (node_type, str(query_key), json.dumps(result_dict)))
            conn.commit()
        except Exception as e:
            print(f"Cache write error: {e}")
        finally:
            conn.close()
