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
                step TEXT DEFAULT 'WAITING_FOR_REGISTRATION_PRINT',
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

        # Validations table to store successful validation events (amount and timestamp)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                validated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        cursor.execute('UPDATE users SET step = ? WHERE user_id = ?', (str(step), user_id))
        self.conn.commit()

    def set_vip(self, user_id, is_vip=True):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET is_vip = ?, step = ? WHERE user_id = ?', (is_vip, 'COMPLETED', user_id))
        self.conn.commit()

    def save_validation(self, user_id, amount: float):
        """Record a successful validation for a user (amount in BRL)."""
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO validations (user_id, amount) VALUES (?, ?)', (user_id, float(amount)))
        # Also mark user as VIP and step completed
        cursor.execute('UPDATE users SET is_vip = 1, step = ? WHERE user_id = ?', ('COMPLETED', user_id))
        self.conn.commit()

    def is_user_validated(self, user_id):
        """Return (is_validated: bool, amount: float|None) based on latest validation record."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT amount FROM validations WHERE user_id = ? ORDER BY validated_at DESC LIMIT 1', (user_id,))
        row = cursor.fetchone()
        if row:
            try:
                return True, float(row[0])
            except Exception:
                return True, None
        # Fallback to users table is_vip flag
        cursor.execute('SELECT is_vip FROM users WHERE user_id = ?', (user_id,))
        row2 = cursor.fetchone()
        if row2 and row2[0]:
            return True, None
        return False, None

    def is_user_vip(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT is_vip FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        return bool(row and row[0])

    def save_message(self, user_id, role, content):
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)', 
                       (user_id, role, content))
        self.conn.commit()

    def increment_interactions(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET interactions = interactions + 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()