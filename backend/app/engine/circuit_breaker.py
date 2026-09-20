"""Exchange Error and Latency Circuit Breaker."""
import time
from typing import Optional
from app.core.constants import CircuitBreakerStatus
from app.core.logger import logger


class CircuitBreaker:
    """
    Monitors consecutive API/network failures and abnormal latency.
    Trips automatically to halt trading if conditions become hazardous.
    """

    def __init__(self, max_consecutive_errors: int = 3, max_latency_ms: float = 2000.0):
        self.max_consecutive_errors = max_consecutive_errors
        self.max_latency_ms = max_latency_ms
        self.consecutive_errors = 0
        self.status = CircuitBreakerStatus.NORMAL
        self.last_trip_time: Optional[float] = None
        self.trip_reason: str = ""
        self.last_error: str = ""

    def record_success(self, latency_ms: float = 0.0) -> None:
        """Records a successful exchange request and resets error counter."""
        if latency_ms > self.max_latency_ms:
            self.status = CircuitBreakerStatus.WARNING
            logger.warning(f"[CIRCUIT BREAKER] High latency warning: {latency_ms:.1f}ms (Threshold: {self.max_latency_ms}ms)")
        else:
            self.consecutive_errors = 0
            if self.status == CircuitBreakerStatus.WARNING:
                self.status = CircuitBreakerStatus.NORMAL

    def record_error(self, error_message: str) -> bool:
        """
        Records an exchange error. Trips the breaker if threshold reached.
        Returns: True if breaker was TRIPPED, False otherwise.
        """
        self.consecutive_errors += 1
        self.last_error = str(error_message)
        logger.error(f"[CIRCUIT BREAKER] Exchange error count: {self.consecutive_errors}/{self.max_consecutive_errors}. Error: {error_message}")

        if self.consecutive_errors >= self.max_consecutive_errors:
            self.status = CircuitBreakerStatus.TRIPPED
            self.last_trip_time = time.time()
            self.trip_reason = f"Tripped after {self.consecutive_errors} consecutive exchange errors: {error_message}"
            logger.error(f"[ALERT: CIRCUIT BREAKER TRIPPED] Trading HALTED. Reason: {self.trip_reason}")
            return True
        return False

    def can_trade(self) -> bool:
        """Returns False if circuit breaker is tripped."""
        return self.status != CircuitBreakerStatus.TRIPPED

    def manual_reset(self) -> None:
        """Resets the circuit breaker to normal status."""
        self.consecutive_errors = 0
        self.status = CircuitBreakerStatus.NORMAL
        self.trip_reason = ""
        self.last_error = ""
        logger.info("[CIRCUIT BREAKER] Breaker manually reset to NORMAL.")
