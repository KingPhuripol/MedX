"""Additive migration and atomic append-only command log.

BEGIN IMMEDIATE makes revision checking and idempotency atomic across connections.
No v1 table is changed. Idempotency keys are actor+resource scoped.
"""
import math
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class DomainError(Exception):
    def __init__(self, status, code, details=None):
        self.status, self.code, self.details = status, code, details
        super().__init__(code)


class Store:
    def __init__(self, path=None):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path or ":memory:"), check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.lock = RLock()
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS v2_migrations(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO v2_migrations VALUES(1);
        CREATE TABLE IF NOT EXISTS v2_records(
          sequence INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL, resource TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS v2_records_lookup ON v2_records(kind,resource,sequence);
        CREATE INDEX IF NOT EXISTS v2_run_id ON v2_records(json_extract(payload,'$.run_id')) WHERE kind='run';
        CREATE INDEX IF NOT EXISTS v2_draft_encounter ON v2_records(json_extract(payload,'$.encounter_id'),sequence) WHERE kind='draft';
        CREATE TABLE IF NOT EXISTS v2_commands(
          actor TEXT NOT NULL, scope TEXT NOT NULL, key TEXT NOT NULL,
          checksum TEXT NOT NULL, result TEXT NOT NULL,
          PRIMARY KEY(actor,scope,key));
        CREATE TABLE IF NOT EXISTS v2_budget(
          sequence INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL);
        ''')
        for table in ("v2_records", "v2_commands", "v2_budget"):
            for action in ("UPDATE", "DELETE"):
                self.conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'append-only'); END")
        self.conn.commit()

    def close(self):
        self.conn.close()

    @contextmanager
    def transaction(self):
        with self.lock:
            nested = self.conn.in_transaction
            if nested:
                savepoint = "s" + __import__("uuid").uuid4().hex
                self.conn.execute(f"SAVEPOINT {savepoint}")
            else:
                self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                if nested:
                    self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    self.conn.commit()
            except BaseException:
                if nested:
                    self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    self.conn.rollback()
                raise

    def all(self, kind, resource=None):
        with self.lock:
            if resource is None:
                rows = self.conn.execute("SELECT payload FROM v2_records WHERE kind=? ORDER BY sequence", (kind,)).fetchall()
            else:
                rows = self.conn.execute("SELECT payload FROM v2_records WHERE kind=? AND resource=? ORDER BY sequence", (kind, resource)).fetchall()
            return [json.loads(r[0]) for r in rows]

    def append(self, kind, resource, payload):
        self.conn.execute("INSERT INTO v2_records(kind,resource,payload) VALUES(?,?,?)", (kind, resource, encoded(payload)))

    def page(self, kind, resource, after=0, limit=25):
        with self.lock:
            rows=self.conn.execute('''SELECT sequence,payload FROM v2_records
                WHERE kind=? AND resource=? AND sequence>? ORDER BY sequence LIMIT ?''',
                (kind,resource,after,limit+1)).fetchall()
        return {'items':[json.loads(r['payload']) for r in rows[:limit]],
                'next_cursor':rows[limit-1]['sequence'] if len(rows)>limit else None}

    def replay(self, actor, scope, key, body):
        row = self.conn.execute("SELECT checksum,result FROM v2_commands WHERE actor=? AND scope=? AND key=?", (actor, scope, key)).fetchone()
        if row:
            if row["checksum"] != digest(body):
                raise DomainError(409, "IDEMPOTENCY_CONFLICT")
            return json.loads(row["result"])

    def remember(self, actor, scope, key, body, result):
        self.conn.execute("INSERT INTO v2_commands VALUES(?,?,?,?,?)", (actor, scope, key, digest(body), encoded(result)))

    def reserve(self, ceiling, amount):
        with self.transaction():
            total = self.conn.execute("SELECT COALESCE(SUM(amount),0) FROM v2_budget").fetchone()[0]
            if not math.isfinite(amount) or not math.isfinite(ceiling) or amount <= 0 or ceiling <= 0 or total + amount > ceiling:
                raise DomainError(429, "PAID_BUDGET_EXCEEDED")
            self.conn.execute("INSERT INTO v2_budget(amount) VALUES(?)", (amount,))
