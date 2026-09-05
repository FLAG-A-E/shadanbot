import shutil
from pathlib import Path

from config import DATABASE_URL, DB_NAME, LEGACY_DB_NAME
from database.connection import get_connection


def column_exists(cursor, table_name, column_name):
    if DATABASE_URL:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
            (table_name, column_name),
        )
        return cursor.fetchone() is not None
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def init_db():
    db_path = Path(DB_NAME)
    legacy_path = Path(LEGACY_DB_NAME)
    if not db_path.exists() and legacy_path.exists():
        shutil.copyfile(legacy_path, db_path)

    conn = get_connection()
    cursor = conn.cursor()
    generated_id = "BIGSERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            gender TEXT,
            degree TEXT,
            department TEXT,
            job_title TEXT,
            possible_jobs TEXT,
            governorate TEXT,
            desired_salary TEXT,
            is_subscribed_alerts INTEGER DEFAULT 0,
            alerts_expires_at DATETIME,
            free_job_posts_used INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS jobs (
            id {generated_id},
            post_hash TEXT UNIQUE,
            job_title TEXT,
            company TEXT,
            location TEXT,
            requirements TEXT,
            contact_info TEXT,
            channel TEXT,
            raw_text TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS cv_requests (
            id {generated_id},
            user_id INTEGER,
            service_type TEXT,
            full_name TEXT,
            phone TEXT,
            experience TEXT,
            skills TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employer_subscriptions (
            employer_id INTEGER PRIMARY KEY,
            plan_type TEXT,
            jobs_left INTEGER DEFAULT 0,
            expires_at DATETIME
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS payments (
            id {generated_id},
            user_id INTEGER,
            order_type TEXT,
            order_id TEXT,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            payment_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            paid_at DATETIME
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_alert_payments (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            payment_account TEXT,
            payment_screenshot_file_id TEXT,
            status TEXT DEFAULT 'pending',
            reviewed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_job_posts (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            job_text TEXT NOT NULL,
            plan_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            payment_account TEXT,
            payment_screenshot_file_id TEXT,
            payment_note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            published_at DATETIME
        )
    """)

    if column_exists(cursor, "jobs", "contact") and not column_exists(cursor, "jobs", "contact_info"):
        cursor.execute("ALTER TABLE jobs ADD COLUMN contact_info TEXT")
        cursor.execute("UPDATE jobs SET contact_info = contact WHERE contact_info IS NULL")

    user_profile_columns = {
        "full_name": "TEXT",
        "gender": "TEXT",
        "degree": "TEXT",
        "department": "TEXT",
        "job_title": "TEXT",
        "possible_jobs": "TEXT",
        "governorate": "TEXT",
        "desired_salary": "TEXT",
        "is_subscribed_alerts": "INTEGER DEFAULT 0",
        "alerts_expires_at": "DATETIME",
        "free_job_posts_used": "INTEGER DEFAULT 0",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_type in user_profile_columns.items():
        if not column_exists(cursor, "user_profiles", column_name):
            cursor.execute(f"ALTER TABLE user_profiles ADD COLUMN {column_name} {column_type}")

    pending_job_columns = {
        "payment_account": "TEXT",
        "payment_screenshot_file_id": "TEXT",
        "payment_note": "TEXT",
    }
    for column_name, column_type in pending_job_columns.items():
        if not column_exists(cursor, "pending_job_posts", column_name):
            cursor.execute(f"ALTER TABLE pending_job_posts ADD COLUMN {column_name} {column_type}")

    if not column_exists(cursor, "jobs", "contact_info"):
        cursor.execute("ALTER TABLE jobs ADD COLUMN contact_info TEXT")

    if not column_exists(cursor, "jobs", "raw_text"):
        cursor.execute("ALTER TABLE jobs ADD COLUMN raw_text TEXT")

    conn.commit()
    conn.close()
