import os
import sqlite3
from cryptography.fernet import Fernet

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "secrets.db"))
KEY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vault.key"))

class SecretsVault:
    def __init__(self):
        self._init_key()
        self._init_db()
        
    def _init_key(self):
        if not os.path.exists(KEY_PATH):
            key = Fernet.generate_key()
            with open(KEY_PATH, "wb") as f:
                f.write(key)
            try:
                os.chmod(KEY_PATH, 0o600)
            except Exception:
                pass
        
        with open(KEY_PATH, "rb") as f:
            self.key = f.read()
        self.fernet = Fernet(self.key)
        
    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS secrets (
                service TEXT PRIMARY KEY,
                encrypted_key TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        
    def set_key(self, service, key_value):
        encrypted = self.fernet.encrypt(key_value.encode()).decode()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO secrets (service, encrypted_key)
            VALUES (?, ?)
        """, (service, encrypted))
        conn.commit()
        conn.close()
        
    def get_key(self, service):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT encrypted_key FROM secrets WHERE service = ?", (service,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            encrypted = row[0]
            try:
                decrypted = self.fernet.decrypt(encrypted.encode()).decode()
                return decrypted
            except Exception:
                return None
        return None

    def list_keys(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT service FROM secrets")
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]
