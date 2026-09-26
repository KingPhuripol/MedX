"""Dev-only seed: three synthetic users. Passwords come from env with documented dev defaults.

Run: ``PYTHONPATH=backend python -m app.seed``. Never use these accounts outside local dev.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, select

from .config import Settings
from .db import create_schema, make_engine, users
from .roles import Role
from .security import hash_password

# (username, role, env var, documented dev-only default — see .env.example)
DEV_USERS: tuple[tuple[str, Role, str, str], ...] = (
    ("nurse1", Role.NURSE, "SEED_NURSE1_PASSWORD", "nurse1-dev-only"),
    ("physician1", Role.PHYSICIAN, "SEED_PHYSICIAN1_PASSWORD", "physician1-dev-only"),
    ("pharmacist1", Role.PHARMACIST, "SEED_PHARMACIST1_PASSWORD", "pharmacist1-dev-only"),
)


def dev_password(env_var: str, default: str) -> str:
    return os.environ.get(env_var, "") or default


def seed_dev_users(engine: Engine) -> int:
    created = 0
    with engine.begin() as conn:
        for username, role, env_var, default in DEV_USERS:
            exists = conn.execute(select(users.c.id).where(users.c.username == username)).first()
            if exists:
                continue
            conn.execute(
                users.insert().values(
                    username=username,
                    role=role.value,
                    password_hash=hash_password(dev_password(env_var, default)),
                )
            )
            created += 1
    return created


def main() -> None:
    engine = make_engine(Settings.from_env().database_url)
    create_schema(engine)
    created = seed_dev_users(engine)
    print(f"seed: {created} dev-only synthetic user(s) created")


if __name__ == "__main__":
    main()
