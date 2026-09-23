"""Durable job status for the supported single API process deployment.

An interrupted job is failed, never replayed automatically. Cancellation is
cooperative: an in-flight HTTP call may finish, but its output is not committed.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import json

from innovation.v2.models import now
from innovation.v2.store import DomainError, encoded


class Jobs:
    def __init__(self, service, workers=4, inline=False):
        self.service, self.inline = service, inline
        self.store = service.store
        self.owner = uuid4().hex
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='frontdoor-job')
        self.cancelled = {}
        with self.store.transaction():
            self.store.conn.execute('''CREATE TABLE IF NOT EXISTS v2_jobs(
                id TEXT PRIMARY KEY, encounter TEXT NOT NULL, actor TEXT NOT NULL,
                owner TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                result TEXT, error TEXT, created_at TEXT NOT NULL)''')
            self.store.conn.execute("CREATE INDEX IF NOT EXISTS v2_jobs_encounter ON v2_jobs(encounter,created_at)")
            self.store.conn.execute("UPDATE v2_jobs SET status='failed',error='PROCESS_INTERRUPTED' WHERE status IN ('queued','running')")

    def get(self, id):
        with self.store.lock:
            row = self.store.conn.execute('SELECT * FROM v2_jobs WHERE id=?', (id,)).fetchone()
        if row is None:
            raise DomainError(404, 'JOB_NOT_FOUND')
        return {'job_id': row['id'], 'encounter_id': row['encounter'], 'status': row['status'],
                'result': json.loads(row['result']) if row['result'] else None,
                'error_code': row['error'], 'created_at': row['created_at']}

    def create(self, encounter, body, actor):
        self.service.require(actor, {'intake', 'physician'})
        def perform():
            self.service.ensure_revision(encounter, body.expected_revision)
            id = uuid4().hex
            self.store.conn.execute('INSERT INTO v2_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                (id, encounter, actor.subject, self.owner, 'queued', encoded(body.model_dump(mode='json')),
                 None, None, now().isoformat()))
            return {'job_id': id}
        result = self.service.command(actor, 'job:' + encounter, body.idempotency_key,
                                      body.model_dump(mode='json'), perform)
        if self.inline:
            self.execute(result['job_id'], body, actor)
        else:
            self.pool.submit(self.execute, result['job_id'], body, actor)
        return self.get(result['job_id'])

    def execute(self, id, body, actor):
        cancel = Event()
        with self.store.transaction():
            changed = self.store.conn.execute("UPDATE v2_jobs SET status='running' WHERE id=? AND status='queued' AND owner=?",
                                              (id, self.owner)).rowcount
            if not changed:
                return
            self.cancelled[id] = cancel
        try:
            result = self.service.turn(self.get(id)['encounter_id'], body, actor, cancel_check=cancel.is_set)
            status = 'cancelled' if result.get('error_code') == 'JOB_CANCELLED' else ('completed' if result['status'] == 'COMPLETED' else 'failed')
            with self.store.transaction():
                self.store.conn.execute('UPDATE v2_jobs SET status=?,result=?,error=? WHERE id=? AND owner=?',
                    (status, encoded(result), result.get('error_code'), id, self.owner))
        except Exception as exc:
            with self.store.transaction():
                self.store.conn.execute("UPDATE v2_jobs SET status='failed',error=? WHERE id=? AND owner=?",
                    (exc.code if isinstance(exc, DomainError) else 'JOB_FAILED', id, self.owner))
        finally:
            with self.store.lock:
                self.cancelled.pop(id, None)

    def cancel(self, id):
        with self.store.transaction():
            job = self.get(id)
            if job['status'] == 'queued':
                self.store.conn.execute("UPDATE v2_jobs SET status='cancelled' WHERE id=?", (id,))
            elif job['status'] == 'running':
                event = self.cancelled.get(id)
                if event:
                    event.set()
        return self.get(id)

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=False)
