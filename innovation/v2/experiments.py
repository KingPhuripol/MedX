"""Bounded offline experiment jobs; experiment state is separate from case storage."""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from typing import Literal
from pydantic import Field
from innovation.v2.models import Model, now
from innovation.v2.store import Store, DomainError, digest


class ExperimentRequest(Model):
    action: Literal['search', 'freeze', 'heldout']
    parent_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    design: str | None = Field(default=None, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)


class Experiments:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.store = Store(self.root / 'experiments.sqlite3')
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='experiment')
        with self.store.transaction():
            for item in self.latest():
                if item['status'] in {'queued', 'running'}:
                    self.store.append('experiment', item['id'], {**item, 'status': 'failed', 'error': 'PROCESS_INTERRUPTED'})

    def latest(self):
        return list({r['id']: r for r in self.store.all('experiment')}.values())

    def get(self, id, actor):
        rows = self.store.all('experiment', id)
        if not rows or rows[-1]['workspace'] != actor.workspace:
            raise DomainError(404, 'EXPERIMENT_NOT_FOUND')
        return rows[-1]

    def create(self, body, actor):
        if actor.role not in {'physician', 'evaluator'}:
            raise DomainError(403, 'ROLE_FORBIDDEN')
        with self.store.transaction():
            cached = self.store.replay(actor.subject, 'experiment', body.idempotency_key, body.model_dump())
            if cached:
                return self.get(cached['id'], actor)
            if any(r['status'] in {'queued', 'running'} for r in self.latest()):
                raise DomainError(409, 'EXPERIMENT_RUNNING')
            if body.action != 'search':
                if not body.parent_id:
                    raise DomainError(422, 'EXPERIMENT_PARENT_REQUIRED')
                parent = self.get(body.parent_id, actor)
                expected = 'search' if body.action == 'freeze' else 'freeze'
                if parent['action'] != expected or parent['status'] != 'completed':
                    raise DomainError(409, 'EXPERIMENT_PARENT_NOT_READY')
                if body.action == 'freeze' and not body.design:
                    raise DomainError(422, 'DESIGN_SELECTION_REQUIRED')
            id = uuid4().hex
            item = {'id': id, 'workspace': actor.workspace, 'actor': actor.subject,
                    'action': body.action, 'status': 'queued', 'created_at': now().isoformat(),
                    'provider': 'mock', 'clinical_verdict': 'NOT_REVIEWED', 'error': None}
            self.store.append('experiment', id, item)
            self.store.remember(actor.subject, 'experiment', body.idempotency_key, body.model_dump(), {'id': id})
        self.pool.submit(self.execute, item, body)
        return item

    def execute(self, item, body):
        with self.store.transaction():
            self.store.append('experiment', item['id'], {**item, 'status': 'running'})
        path = self.root / (item['id'] + '.json')
        command = [sys.executable, '-m', 'innovation.v2.evaluation', body.action,
                   '--provider', 'mock', '--suite', 'families', '--workers', '2', '--output', str(path)]
        if body.parent_id:
            command += ['--input', str(self.root / (body.parent_id + '.json'))]
        if body.design:
            command += ['--design', body.design]
        try:
            result = subprocess.run(command, capture_output=True, timeout=600,
                                    cwd=Path(__file__).resolve().parents[2])
            if result.returncode != 0:
                raise ValueError('Experiment failed')
            report = json.loads(path.read_text())
            completed = {**item, 'status': 'completed', 'report_hash': digest(report)}
        except Exception:
            completed = {**item, 'status': 'failed', 'error': 'EXPERIMENT_FAILED_CHECK_MANIFEST_AND_SELECTION'}
        with self.store.transaction():
            self.store.append('experiment', item['id'], completed)

    def report(self, id, actor):
        item = self.get(id, actor)
        if item['status'] != 'completed':
            raise DomainError(409, 'EXPERIMENT_NOT_COMPLETED')
        report = json.loads((self.root / (id + '.json')).read_text())
        if digest(report) != item['report_hash']:
            raise DomainError(409, 'EXPERIMENT_ARTIFACT_CHANGED')
        def compact(value):
            if isinstance(value, dict):
                return {key: compact(item) for key, item in value.items() if key not in {'results', 'tested'}}
            if isinstance(value, list):
                return [compact(item) for item in value]
            return value
        return compact(report)

    def close(self):
        self.pool.shutdown(wait=True)
        self.store.close()
