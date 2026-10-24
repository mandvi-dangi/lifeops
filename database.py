import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("lifeops.db")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_date TEXT,
            priority TEXT NOT NULL DEFAULT 'medium',
            estimate_minutes INTEGER NOT NULL DEFAULT 30,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        existing = {row[1] for row in c.execute("PRAGMA table_info(tasks)").fetchall()}
        migrations = {
            "task_type": "TEXT NOT NULL DEFAULT 'task'",
            "course": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'Not started'",
            "instructions": "TEXT",
            "submitted_at": "TEXT",
            "source_file": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in existing:
                c.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")
        c.execute("""
        CREATE TABLE IF NOT EXISTS reminder_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            days_before INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(task_id, days_before, due_date),
            FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )""")


def list_tasks(task_type=None):
    query = "SELECT * FROM tasks"
    params = []
    if task_type:
        query += " WHERE task_type=?"
        params.append(task_type)
    query += " ORDER BY completed, due_date IS NULL, due_date, CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id"
    with connect() as c:
        return [dict(r) for r in c.execute(query, params).fetchall()]


def add_task(title, due_date=None, priority="medium", estimate_minutes=30,
             task_type="task", course=None, instructions=None, source_file=None):
    status = "Submitted" if task_type == "assignment" and False else "Not started"
    with connect() as c:
        cur = c.execute("""
            INSERT INTO tasks(title,due_date,priority,estimate_minutes,task_type,course,status,instructions,source_file)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (title, due_date, priority, estimate_minutes, task_type, course, status, instructions, source_file))
        return cur.lastrowid


def update_task(task_id, **fields):
    allowed = {"title", "due_date", "priority", "estimate_minutes", "completed", "course", "status", "instructions", "submitted_at", "source_file"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return False
    if fields.get("status") == "Submitted":
        from datetime import datetime
        fields.setdefault("submitted_at", datetime.now().astimezone().isoformat(timespec="seconds"))
        fields["completed"] = 1
    elif fields.get("status") in ("Not started", "In progress"):
        fields["submitted_at"] = None
        fields["completed"] = 0
    assignments = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        cur = c.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*fields.values(), task_id))
        return cur.rowcount == 1


def complete_task(task_id):
    return update_task(task_id, completed=1, status="Submitted")


def delete_task(task_id):
    with connect() as c:
        cur = c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        return cur.rowcount == 1


def reminder_was_sent(task_id, days_before, due_date):
    with connect() as c:
        return c.execute("SELECT 1 FROM reminder_log WHERE task_id=? AND days_before=? AND due_date=?",
                         (task_id, days_before, due_date)).fetchone() is not None


def record_reminder(task_id, days_before, due_date):
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO reminder_log(task_id,days_before,due_date) VALUES(?,?,?)",
                  (task_id, days_before, due_date))
