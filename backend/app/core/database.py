"""Async SQLAlchemy engine/session setup for the Supabase Postgres database."""
from collections.abc import AsyncGenerator

from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Stub for Supabase's auth.users table, which we don't manage (no model, never
# migrated) but need registered so our own tables can declare a ForeignKey to
# it (tasks.user_id -> auth.users.id).
auth_users_table = Table(
    "users",
    Base.metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    schema="auth",
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
