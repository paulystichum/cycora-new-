"""SQLite storage for Cycora. All health records are linked to a local profile ID."""
from pathlib import Path
import sqlite3
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "cycora.db"


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            birth_year INTEGER NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'Myself',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS period_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            start_date TEXT NOT NULL,
            end_date TEXT,
            flow TEXT NOT NULL DEFAULT 'Not recorded',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(profile_id, start_date)
        );
        CREATE TABLE IF NOT EXISTS symptom_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            log_date TEXT NOT NULL,
            symptom TEXT NOT NULL,
            intensity TEXT NOT NULL DEFAULT 'Mild',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            note_date TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS profile_answers (
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            answer_key TEXT NOT NULL,
            answer_value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY(profile_id, answer_key)
        );
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            activity_type TEXT NOT NULL,
            log_date TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_period_profile ON period_logs(profile_id, start_date);
        CREATE INDEX IF NOT EXISTS idx_symptom_profile ON symptom_logs(profile_id, log_date);
        CREATE INDEX IF NOT EXISTS idx_notes_profile ON notes(profile_id, note_date);
        """)


def now_text():
    return datetime.now().isoformat(timespec="seconds")


def list_profiles():
    with connect() as conn:
        return conn.execute("SELECT * FROM profiles ORDER BY name COLLATE NOCASE, id").fetchall()


def get_profile(profile_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()


def create_profile(name, birth_year, purpose):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO profiles(name,birth_year,purpose,created_at) VALUES(?,?,?,?)",
            (name.strip(), birth_year, purpose, now_text()),
        )
        return cur.lastrowid


def update_profile(profile_id, name, birth_year, purpose):
    with connect() as conn:
        conn.execute("UPDATE profiles SET name=?, birth_year=?, purpose=? WHERE id=?",
                     (name.strip(), birth_year, purpose, profile_id))


def delete_profile(profile_id):
    with connect() as conn:
        conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))


def list_periods(profile_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM period_logs WHERE profile_id=? ORDER BY start_date DESC", (profile_id,)).fetchall()


def add_period(profile_id, start_date, end_date=None, flow="Not recorded", notes=""):
    with connect() as conn:
        conn.execute("INSERT INTO period_logs(profile_id,start_date,end_date,flow,notes,created_at) VALUES(?,?,?,?,?,?)",
                     (profile_id, start_date, end_date or None, flow, notes.strip(), now_text()))


def update_period_end(period_id, profile_id, end_date):
    with connect() as conn:
        conn.execute("UPDATE period_logs SET end_date=? WHERE id=? AND profile_id=?", (end_date or None, period_id, profile_id))


def delete_period(period_id, profile_id):
    with connect() as conn:
        conn.execute("DELETE FROM period_logs WHERE id=? AND profile_id=?", (period_id, profile_id))


def add_symptom(profile_id, log_date, symptom, intensity, notes=""):
    with connect() as conn:
        conn.execute("INSERT INTO symptom_logs(profile_id,log_date,symptom,intensity,notes,created_at) VALUES(?,?,?,?,?,?)",
                     (profile_id, log_date, symptom, intensity, notes.strip(), now_text()))


def list_symptoms(profile_id, limit=100):
    with connect() as conn:
        return conn.execute("SELECT * FROM symptom_logs WHERE profile_id=? ORDER BY log_date DESC, id DESC LIMIT ?",
                             (profile_id, limit)).fetchall()


def delete_symptom(symptom_id, profile_id):
    with connect() as conn:
        conn.execute("DELETE FROM symptom_logs WHERE id=? AND profile_id=?", (symptom_id, profile_id))


def add_note(profile_id, note_date, body):
    with connect() as conn:
        conn.execute("INSERT INTO notes(profile_id,note_date,body,created_at) VALUES(?,?,?,?)",
                     (profile_id, note_date, body.strip(), now_text()))


def list_notes(profile_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM notes WHERE profile_id=? ORDER BY note_date DESC, id DESC", (profile_id,)).fetchall()


def delete_note(note_id, profile_id):
    with connect() as conn:
        conn.execute("DELETE FROM notes WHERE id=? AND profile_id=?", (note_id, profile_id))


def save_profile_answers(profile_id, answers):
    with connect() as conn:
        for key, value in answers.items():
            if isinstance(value, (list, tuple, set)):
                import json
                value = json.dumps(list(value), ensure_ascii=False)
            elif not isinstance(value, str):
                value = str(value)
            conn.execute("INSERT INTO profile_answers(profile_id,answer_key,answer_value,updated_at) VALUES(?,?,?,?) ON CONFLICT(profile_id,answer_key) DO UPDATE SET answer_value=excluded.answer_value, updated_at=excluded.updated_at", (profile_id, key, value, now_text()))


def get_profile_answers(profile_id):
    import json
    with connect() as conn:
        rows = conn.execute("SELECT answer_key,answer_value FROM profile_answers WHERE profile_id=?", (profile_id,)).fetchall()
    result = {}
    for row in rows:
        value = row["answer_value"]
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            pass
        result[row["answer_key"]] = value
    return result


def add_activity(profile_id, activity_type, log_date, details=''):
    with connect() as conn:
        conn.execute("INSERT INTO activity_logs(profile_id,activity_type,log_date,details,created_at) VALUES(?,?,?,?,?)", (profile_id, activity_type, log_date, details.strip(), now_text()))


def list_activities(profile_id, activity_type=None, limit=100):
    with connect() as conn:
        if activity_type:
            return conn.execute("SELECT * FROM activity_logs WHERE profile_id=? AND activity_type=? ORDER BY log_date DESC,id DESC LIMIT ?", (profile_id, activity_type, limit)).fetchall()
        return conn.execute("SELECT * FROM activity_logs WHERE profile_id=? ORDER BY log_date DESC,id DESC LIMIT ?", (profile_id, limit)).fetchall()


def delete_activity(activity_id, profile_id):
    with connect() as conn:
        conn.execute("DELETE FROM activity_logs WHERE id=? AND profile_id=?", (activity_id, profile_id))
