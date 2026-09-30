"""
In-memory provider cooldown state.

This prevents every Assistant request from repeatedly hitting
a provider which has just returned a rate limit or temporary
availability failure.

No API credentials are stored here.
"""

import threading
import time


class ProviderCooldownManager:
    def __init__(
        self,
        clock=None,
    ):
        self._clock = (
            clock
            or time.monotonic
        )

        self._lock = (
            threading.RLock()
        )

        self._cooldowns = {}

    def set(
        self,
        provider,
        seconds,
        *,
        reason=None,
    ):
        provider = str(
            provider
        ).strip().lower()

        seconds = max(
            1.0,
            float(seconds),
        )

        until = (
            self._clock()
            + seconds
        )

        with self._lock:
            self._cooldowns[
                provider
            ] = {
                "until": until,
                "reason": reason,
            }

    def active(
        self,
        provider,
    ):
        provider = str(
            provider
        ).strip().lower()

        with self._lock:
            item = self._cooldowns.get(
                provider
            )

            if not item:
                return False

            if (
                item["until"]
                <= self._clock()
            ):
                self._cooldowns.pop(
                    provider,
                    None,
                )

                return False

            return True

    def remaining(
        self,
        provider,
    ):
        provider = str(
            provider
        ).strip().lower()

        with self._lock:
            item = self._cooldowns.get(
                provider
            )

            if not item:
                return 0.0

            remaining = (
                item["until"]
                - self._clock()
            )

            if remaining <= 0:
                self._cooldowns.pop(
                    provider,
                    None,
                )

                return 0.0

            return remaining

    def reason(
        self,
        provider,
    ):
        provider = str(
            provider
        ).strip().lower()

        with self._lock:
            item = self._cooldowns.get(
                provider
            )

            if not item:
                return None

            if not self.active(
                provider
            ):
                return None

            return item.get(
                "reason"
            )

    def clear(
        self,
        provider=None,
    ):
        with self._lock:
            if provider is None:
                self._cooldowns.clear()

                return

            self._cooldowns.pop(
                str(
                    provider
                ).strip().lower(),
                None,
            )

    def snapshot(
        self,
    ):
        result = {}

        with self._lock:
            for provider in list(
                self._cooldowns
            ):
                remaining = (
                    self.remaining(
                        provider
                    )
                )

                if remaining <= 0:
                    continue

                result[
                    provider
                ] = {
                    "remaining_seconds": (
                        round(
                            remaining,
                            1,
                        )
                    ),
                    "reason": (
                        self.reason(
                            provider
                        )
                    ),
                }

        return result


provider_cooldowns = (
    ProviderCooldownManager()
)
