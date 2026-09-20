"""Symbol Metadata and Precision Rules Cache."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional
from app.core.decimal_math import to_decimal
from app.core.logger import logger


@dataclass
class SymbolRules:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_notional: Decimal
    min_amount: Decimal
    max_amount: Decimal
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal


class SymbolRulesCache:
    """Thread-safe cache for market metadata and precision rules."""

    def __init__(self):
        self._rules: Dict[str, SymbolRules] = {}

    def parse_and_store_from_ccxt(self, market: dict) -> SymbolRules:
        symbol = market.get("symbol", "")
        precision = market.get("precision", {})
        limits = market.get("limits", {})
        
        # Safe extraction of tick size (price precision)
        tick_size = to_decimal(precision.get("price", "0.01"))
        if tick_size > Decimal("1") or tick_size <= Decimal("0"):
            # If precision is given as number of decimal digits (e.g. 2 -> 0.01)
            try:
                digits = int(precision.get("price", 2))
                tick_size = Decimal("1") / (Decimal("10") ** digits)
            except Exception as e:
                logger.warning(
                    f"[SYMBOL RULES] tick_size parse failed for '{symbol}' "
                    f"(precision={precision.get('price')}), using default 0.01. Error: {e}"
                )
                tick_size = Decimal("0.01")

        # Safe extraction of step size (amount precision)
        step_size = to_decimal(precision.get("amount", "0.001"))
        if step_size > Decimal("1") or step_size <= Decimal("0"):
            try:
                digits = int(precision.get("amount", 3))
                step_size = Decimal("1") / (Decimal("10") ** digits)
            except Exception as e:
                logger.warning(
                    f"[SYMBOL RULES] step_size parse failed for '{symbol}' "
                    f"(precision={precision.get('amount')}), using default 0.001. Error: {e}"
                )
                step_size = Decimal("0.001")

        min_cost = limits.get("cost", {}).get("min") if limits.get("cost") else None
        min_notional = to_decimal(min_cost) if min_cost is not None else Decimal("5.0")
        
        min_amount = to_decimal(limits.get("amount", {}).get("min", "0.0001"))
        max_amount = to_decimal(limits.get("amount", {}).get("max", "1000000.0"))
        
        maker_fee = to_decimal(market.get("maker", "0.001"))
        taker_fee = to_decimal(market.get("taker", "0.001"))

        rules = SymbolRules(
            symbol=symbol,
            tick_size=tick_size,
            step_size=step_size,
            min_notional=min_notional,
            min_amount=min_amount,
            max_amount=max_amount,
            maker_fee_rate=maker_fee,
            taker_fee_rate=taker_fee
        )
        self._rules[symbol] = rules
        return rules

    def get_rules(self, symbol: str) -> Optional[SymbolRules]:
        return self._rules.get(symbol)


symbol_rules_cache = SymbolRulesCache()
