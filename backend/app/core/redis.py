"""Async Redis client for Upstash.

Redis here is scratch space only (AI conversation state). It is never the
system of record — PostgreSQL/Supabase is.

Upstash closes idle connections. Without these settings the client reuses a
dead pooled connection and the first command after a quiet period fails
("connection was aborted"): health checks re-validate a connection idle for
30s+, and a dropped connection is retried on a fresh one.
"""
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError

from app.core.config import settings

redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    health_check_interval=30,
    socket_keepalive=True,
    retry=Retry(ExponentialBackoff(cap=2, base=0.2), retries=3),
    retry_on_error=[ConnectionError, TimeoutError],
)
