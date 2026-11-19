"""Proves every Alembic migration can be applied AND rolled back, without
touching the real database.

Creates a temporary database (aitm_migration_check) on the same Postgres
server, adds a stub auth.users table (Supabase provides the real one), then
runs: upgrade head -> downgrade base -> upgrade head, checking the schema at
each point. The temporary database is always dropped at the end.

Run from the backend folder:
    .venv\\Scripts\\python manual\\check_migrations.py
"""
import asyncio
import os

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402

SCRATCH_DB = "aitm_migration_check"


def scratch_url() -> str:
    # Replace only the database name: the last path segment of the URL.
    base, _db = settings.database_url.rsplit("/", 1)
    return f"{base}/{SCRATCH_DB}"


def alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": scratch_url()}  # env var beats .env
    print(f"$ alembic {' '.join(args)}")
    result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
                            capture_output=True, text=True)
    steps = [line.split("Running ")[-1] for line in result.stderr.splitlines() if "Running " in line]
    print(f"  {len(steps)} migration steps" + (f": first '{steps[0][:70]}', last '{steps[-1][:70]}'" if steps else ""))
    if result.returncode != 0:
        print(result.stderr[-2500:])
        raise SystemExit(f"FAILED: alembic {' '.join(args)}")


async def snapshot(engine) -> dict:
    async with engine.connect() as c:
        tables = set((await c.execute(text(
            "select tablename from pg_tables where schemaname='public'"))).scalars())
        enum_rows = (await c.execute(text(
            "select t.typname, e.enumlabel from pg_type t join pg_namespace n on n.oid=t.typnamespace "
            "join pg_enum e on e.enumtypid = t.oid where n.nspname='public' order by t.typname, e.enumsortorder"
        ))).all()
        enums = {}
        for name, label in enum_rows:
            enums.setdefault(name, []).append(label)
        fks = set((await c.execute(text(
            "select conname from pg_constraint where contype='f' and connamespace='public'::regnamespace"
        ))).scalars())
        status_default = (await c.execute(text(
            "select column_default from information_schema.columns "
            "where table_schema='public' and table_name='tasks' and column_name='status'"))).scalar()
    return {"tables": tables, "enums": enums, "fks": fks, "status_default": status_default}


async def main() -> None:
    admin = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f"drop database if exists {SCRATCH_DB} with (force)"))
        await c.execute(text(f"create database {SCRATCH_DB}"))
    print(f"created temporary database {SCRATCH_DB}")
    scratch = create_async_engine(scratch_url())
    failures = []
    try:
        async with scratch.begin() as c:
            await c.execute(text("create schema auth"))
            await c.execute(text("create table auth.users (id uuid primary key)"))

        alembic("upgrade", "head")
        up = await snapshot(scratch)
        print(f"  after upgrade: {len(up['tables'])} tables, enums {dict((k, len(v)) for k, v in sorted(up['enums'].items()))}, "
              f"FKs incl. tasks_user_id_fkey={'tasks_user_id_fkey' in up['fks']}, "
              f"status default {up['status_default']}")
        if "tasks_user_id_fkey" not in up["fks"]:
            failures.append("tasks_user_id_fkey missing after upgrade")
        if not str(up["status_default"]).startswith("'PENDING'"):
            failures.append(f"unexpected status default {up['status_default']}")

        alembic("downgrade", "base")
        down = await snapshot(scratch)
        leftover_tables = down["tables"] - {"alembic_version"}
        leftover_enums = set(down["enums"])  # every custom type must be gone, not just a known list
        print(f"  after downgrade: leftover tables {sorted(leftover_tables) or 'none'}, "
              f"leftover enums {sorted(leftover_enums) or 'none'}")
        if leftover_tables:
            failures.append(f"tables left after downgrade: {sorted(leftover_tables)}")
        if leftover_enums:
            failures.append(f"enum types left after downgrade: {sorted(leftover_enums)}")

        alembic("upgrade", "head")
        again = await snapshot(scratch)
        same = again == up
        print(f"  after re-upgrade: schema identical to first upgrade = {same}")
        if not same:
            failures.append("schema differs after down/up cycle")
    finally:
        await scratch.dispose()
        async with admin.connect() as c:
            await c.execute(text(f"drop database if exists {SCRATCH_DB} with (force)"))
        await admin.dispose()
        print(f"dropped temporary database {SCRATCH_DB}")

    if failures:
        raise SystemExit("MIGRATION CHECK FAILED:\n- " + "\n- ".join(failures))
    print("MIGRATION CHECK PASSED: every migration upgrades and rolls back cleanly")


if __name__ == "__main__":
    asyncio.run(main())
