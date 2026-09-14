"""SQLite online backup/restore to a new destination; never overwrite a database.

Usage: python -m innovation.v2.backup SOURCE DESTINATION
Stop the application before selecting a restored database as the active store.
"""
import argparse
import sqlite3
from pathlib import Path


def copy_database(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError('Source database does not exist')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents accidental overwrite of a live DB.
    with destination.open('xb'):
        pass
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup integrity check failed')
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    print(copy_database(args.source,args.destination))

if __name__=='__main__':
    main()
