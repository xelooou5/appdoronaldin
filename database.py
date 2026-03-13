import sqlite3
import logging
from datetime import datetime

log = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name="bot_database.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                step INTEGER DEFAULT 0,  -- 0: New, 1: Reg. Print, 2: Dep. Print, 3: Completed
                is_vip BOOLEAN DEFAULT 0,
                interactions INTEGER DEFAULT 0
            )
        ''')
        
        # Messages log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def create_or_update_user(self, user_id, username, first_name):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if cursor.fetchone():
            cursor.execute('''
                UPDATE users SET username = ?, first_name = ? WHERE user_id = ?
            ''', (username, first_name, user_id))
        else:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)
            ''', (user_id, username, first_name))
        self.conn.commit()

    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'joined_at': row[3],
                'step': row[4],
                'is_vip': bool(row[5]),
                'interactions': row[6]
            }
        return None

    def set_user_step(self, user_id, step):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET step = ? WHERE user_id = ?', (step, user_id))
        self.conn.commit()

    def set_vip(self, user_id, is_vip=True):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET is_vip = ?, step = 3 WHERE user_id = ?', (is_vip, user_id))
        self.conn.commit()

    def save_message(self, user_id, role, content):
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)', 
                       (user_id, role, content))
        self.conn.commit()

    def increment_interactions(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET interactions = interactions + 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
