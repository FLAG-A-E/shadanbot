import re
import sqlite3

from config import DATABASE_URL, DB_NAME

try:
    import psycopg
except ImportError:
    psycopg = None


class DatabaseError:
    IntegrityError = (sqlite3.IntegrityError, psycopg.errors.UniqueViolation) if psycopg else sqlite3.IntegrityError


def _translate_sql(sql):
    ignore_insert = "INSERT OR IGNORE" in sql
    sql = sql.replace("INSERT OR IGNORE", "INSERT")
    if ignore_insert and "ON CONFLICT" not in sql:
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    sql = sql.replace("datetime('now', '+30 days')", "CURRENT_TIMESTAMP + INTERVAL '30 days'")
    sql = sql.replace("datetime('now')", "CURRENT_TIMESTAMP")
    sql = sql.replace("DATETIME", "TIMESTAMP")
    sql = sql.replace("ON CONFLICT DO NOTHING", "ON CONFLICT DO NOTHING")
    return sql.replace("?", "%s")


class CursorProxy:
    def __init__(self, cursor, postgres):
        self._cursor = cursor
        self._postgres = postgres

    def execute(self, sql, params=()):
        if self._postgres:
            sql = _translate_sql(sql)
        self._cursor.execute(sql, params)
        return self

    def executemany(self, sql, params):
        if self._postgres:
            sql = _translate_sql(sql)
        self._cursor.executemany(sql, params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    @property
    def rowcount(self):
        return self._cursor.rowcount


class ConnectionProxy:
    def __init__(self, connection, postgres):
        self._connection = connection
        self.postgres = postgres

    def cursor(self):
        return CursorProxy(self._connection.cursor(), self.postgres)

    def execute(self, sql, params=()):
        return CursorProxy(self._connection.cursor(), self.postgres).execute(sql, params)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


def get_connection():
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError("ثبت psycopg[binary] مطلوب عند استخدام DATABASE_URL")
        return ConnectionProxy(psycopg.connect(DATABASE_URL), postgres=True)
    return ConnectionProxy(sqlite3.connect(DB_NAME), postgres=False)
