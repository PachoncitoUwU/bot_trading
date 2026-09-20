"""Server Time Synchronization & Clock Drift Checker."""
import time
from typing import Tuple


class TimeSyncManager:
    """
    Monitors clock drift between the local system and exchange servers.
    Provides offset compensation so timestamps are always aligned.
    """

    def __init__(self, max_allowed_drift_ms: int = 1000):
        self.max_allowed_drift_ms = max_allowed_drift_ms
        self.time_offset_ms: int = 0
        self.is_synced: bool = False

    def get_local_timestamp_ms(self) -> int:
        """Returns current local Unix timestamp in milliseconds."""
        return int(time.time() * 1000)

    def get_adjusted_timestamp_ms(self) -> int:
        """Returns the synchronized timestamp accounting for server drift."""
        return self.get_local_timestamp_ms() + self.time_offset_ms

    def sync_with_server_time(self, server_timestamp_ms: int) -> Tuple[bool, int]:
        """
        Updates the internal offset given an exchange server timestamp.
        Returns: (is_healthy, drift_ms)
        """
        local_ms = self.get_local_timestamp_ms()
        drift_ms = server_timestamp_ms - local_ms
        self.time_offset_ms = drift_ms
        self.is_synced = True

        is_healthy = abs(drift_ms) <= self.max_allowed_drift_ms
        return is_healthy, drift_ms


time_sync_manager = TimeSyncManager(max_allowed_drift_ms=1000)
