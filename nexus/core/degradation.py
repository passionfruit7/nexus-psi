from dataclasses import dataclass
from typing import Any


@dataclass
class DegradedResult:
    """
    Represents an honest result when a dependency is unavailable.
    """

    value: Any
    status: str
    dependency_available: bool
    degraded: bool
    reason: str


class DegradationManager:
    """
    Provides explicit healthy/degraded results.

    The manager never labels a fallback value as healthy.
    """

    def healthy(self, value):
        return DegradedResult(
            value=value,
            status="HEALTHY",
            dependency_available=True,
            degraded=False,
            reason="dependency_available",
        )

    def degraded(
        self,
        fallback_value=None,
        *,
        reason="dependency_unavailable",
    ):
        return DegradedResult(
            value=fallback_value,
            status="DEGRADED",
            dependency_available=False,
            degraded=True,
            reason=reason,
        )

    def resolve(
        self,
        fetch,
        *,
        fallback=None,
    ):
        """
        Try to obtain the live value.

        If the dependency fails, return the fallback while
        explicitly marking the result as DEGRADED.
        """

        try:
            value = fetch()

            return self.healthy(value)

        except Exception as error:
            return self.degraded(
                fallback,
                reason=(
                    f"dependency_unavailable:"
                    f"{type(error).__name__}"
                ),
            )
