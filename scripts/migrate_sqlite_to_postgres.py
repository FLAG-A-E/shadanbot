import os
import sqlite3
import sys

import psycopg


TABLES = {
    "user_profiles": [
        "user_id", "full_name", "gender", "degree", "department", "job_title",
        "possible_jobs", "governorate", "desired_salary", "is_subscribed_alerts",
        "alerts_expires_at", "free_job_posts_used", "updated_at",
    ],
    "jobs": [
        "id", "post_hash", "job_title", "company", "location", "requirements",
        "contact_info", "channel", "raw_text", "created_at",
    ],
    "cv_requests": [
        "id", "user_id", "service_type", "full_name", "phone", "experience",
        "skills", "status", "created_at",
    ],
    "employer_subscriptions": ["employer_id", "plan_type", "jobs_left", "expires_at"],
    "payments": [
        "id", "user_id", "order_type", "order_id", "amount", "status", "payment_url",
        "created_at", "paid_at",
    ],
    "pending_job_posts": [
        "order_id", "user_id", "job_text", "plan_type", "status", "payment_account",
        "payment_screenshot_file_id", "payment_note", "created_at", "published_at",
    ],
    "pending_alert_payments": [
        "order_id", "user_id", "payment_account", "payment_screenshot_file_id",
        "status", "reviewed_at", "created_at",
    ],
}


def migrate(source_path, database_url):
    source = sqlite3.connect(source_path)
    target = psycopg.connect(database_url)
    try:
        for table, columns in TABLES.items():
            quoted_columns = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            rows = source.execute(f"SELECT {quoted_columns} FROM {table}").fetchall()
            if not rows:
                continue
            target.executemany(
                f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                rows,
            )
            print(f"{table}: {len(rows)} rows")
        for table in ("jobs", "cv_requests", "payments"):
            target.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{table}\"), 1), true)"
            )
        target.commit()
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.getenv("DATABASE_URL"):
        raise SystemExit("Usage: DATABASE_URL=... python scripts/migrate_sqlite_to_postgres.py path/to/shadan_database.db")
    migrate(sys.argv[1], os.environ["DATABASE_URL"])