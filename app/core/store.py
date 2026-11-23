"""Assinantes e eventos já processados, em SQLite."""
import sqlite3
import threading
from datetime import date


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock, self.db:
            self.db.execute("create table if not exists users (phone text primary key, status text not null, "
                            "paid_until text)")
            self.db.execute("create table if not exists events (id text primary key)")

    def seen(self, event_id):
        with self.lock:
            return self.db.execute("select 1 from events where id = ?", (event_id,)).fetchone() is not None

    def mark(self, event_id):
        with self.lock, self.db:
            self.db.execute("insert or ignore into events (id) values (?)", (event_id,))

    def set_status(self, phone, status, paid_until=None):
        with self.lock, self.db:
            self.db.execute("insert into users (phone, status, paid_until) values (?, ?, ?) on conflict(phone) do "
                            "update set status = excluded.status, paid_until = coalesce(excluded.paid_until, "
                            "users.paid_until)", (phone, status, paid_until and paid_until.isoformat()))

    def user(self, phone):
        with self.lock:
            row = self.db.execute("select status, paid_until from users where phone = ?", (phone,)).fetchone()
        return None if row is None else {"status": row[0], "paid_until": row[1] and date.fromisoformat(row[1])}

    def has_access(self, phone, today=None):
        u = self.user(phone)
        return bool(u and u["status"] == "active" and u["paid_until"] and u["paid_until"] >= (today or date.today()))
