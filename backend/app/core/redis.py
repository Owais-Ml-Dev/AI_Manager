"""Async Redis client for Upstash.

Redis here is scratch space only (AI conversation state in phase 4+). It is
never the system of record — PostgreSQL/Supabase is.
"""
from redis.asyncio import Redis

from app.core.config import settings

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
