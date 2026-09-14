"""Prevent two API processes from recovering each other's active jobs."""
import fcntl
from pathlib import Path


class ProcessOwnership:
    def __init__(self, database):
        path=Path(str(Path(database).resolve())+'.api.lock')
        path.parent.mkdir(parents=True,exist_ok=True)
        self.file=path.open('a')
        try:fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            raise RuntimeError('This database already has an API owner; run exactly one API process') from None

    def close(self):
        self.file.close()
