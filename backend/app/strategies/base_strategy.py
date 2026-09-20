"""Base Strategy Interface for Modular Trading Rules and Pattern Detectors."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.core.constants import SignalType


@dataclass
class StrategySignal:
    symbol: str
    signal_type: SignalType
    price: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    confidence: Decimal = Decimal("1.0")
    pattern_name: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    Abstract Base Strategy.
    Any custom rule, chart pattern detector, or multi-indicator logic
    inherits from this class without modifying the execution core.
    """

    def __init__(self, name: str, symbols: List[str], timeframe: str = "1h", params: Optional[Dict[str, Any]] = None):
        self.name = name
        self.symbols = symbols
        self.timeframe = timeframe
        self.params = params or {}

    @abstractmethod
    def generate_signals(self, market_data: Dict[str, Any], open_positions: Dict[str, Any]) -> List[StrategySignal]:
        """
        Evaluates candles and market conditions to produce trading signals.
        market_data: dict mapping symbol -> list of OHLCV candles [[time, o, h, l, c, v], ...]
        """
        pass

    def get_parameters(self) -> Dict[str, Any]:
        """Returns strategy parameters for backtesting & optimization."""
        return self.params

    def update_parameters(self, new_params: Dict[str, Any]) -> None:
        """Dynamically updates strategy hyperparameters."""
        self.params.update(new_params)
