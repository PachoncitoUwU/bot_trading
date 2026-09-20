"""Forward-Testing Engine and Statistical Rigor Tracker.

Manages the 300-trade Demo validation cycle:
- Zero martingale: Fixed 0.25% stake ($25 USD).
- Per-pattern breakdown (wins, losses, win rate, net PnL).
- Statistical 95% Wilson Score confidence intervals.
- Automated Telegram milestone reports every 50 trades.
"""
import os
import json
import math
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from app.core.logger import logger


class ForwardTestTracker:
    def __init__(self, target_trades: int = 300, milestone_interval: int = 50):
        self.target_trades = target_trades
        self.milestone_interval = milestone_interval
        self.storage_file = os.path.join(os.path.dirname(__file__), "forward_test_data.json")
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[FORWARD TEST] Error loading data: {e}. Reinitializing.")
        return {
            "cycle_active": True,
            "start_time": datetime.utcnow().isoformat(),
            "target_trades": self.target_trades,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "net_pnl": 0.0,
            "starting_balance": 9902.58,
            "current_balance": 9902.58,
            "peak_balance": 9902.58,
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "patterns": {},
            "trades": []
        }

    def _save(self) -> None:
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"[FORWARD TEST] Failed to save tracker data: {e}")

    def calculate_confidence_interval(self, wins: int, total: int, confidence: float = 0.95) -> Tuple[float, float]:
        """Calculates two-sided Wilson score interval for binomial proportion."""
        if total <= 0:
            return 0.0, 0.0
        z = 1.96 if confidence == 0.95 else 2.576 # 95% vs 99%
        p = wins / total
        denominator = 1.0 + (z ** 2) / total
        center = (p + (z ** 2) / (2.0 * total)) / denominator
        spread = (z * math.sqrt((p * (1.0 - p) / total) + ((z ** 2) / (4.0 * (total ** 2))))) / denominator
        lower = max(0.0, center - spread) * 100.0
        upper = min(1.0, center + spread) * 100.0
        return round(lower, 2), round(upper, 2)

    def record_trade(
        self,
        symbol: str,
        pattern: str,
        side: str,
        stake: float,
        is_win: bool,
        profit_usd: float,
        current_balance: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        Records a completed forward-test trade.
        Returns (is_milestone: bool, milestone_message: Optional[str]).
        """
        self.data["total_trades"] += 1
        trade_num = self.data["total_trades"]

        if is_win:
            self.data["wins"] += 1
        else:
            self.data["losses"] += 1

        self.data["net_pnl"] = round(self.data["net_pnl"] + profit_usd, 2)
        self.data["current_balance"] = round(current_balance, 2)

        # Drawdown tracking
        if current_balance > self.data["peak_balance"]:
            self.data["peak_balance"] = current_balance
        dd_usd = self.data["peak_balance"] - current_balance
        if dd_usd > self.data["max_drawdown_usd"]:
            self.data["max_drawdown_usd"] = round(dd_usd, 2)
            self.data["max_drawdown_pct"] = round((dd_usd / self.data["peak_balance"]) * 100.0, 2)

        # Pattern stats
        clean_pat = pattern if pattern and pattern != "Neutral" else "General Sniper Confluence"
        if clean_pat not in self.data["patterns"]:
            self.data["patterns"][clean_pat] = {"wins": 0, "losses": 0, "net_pnl": 0.0, "win_rate": 0.0}

        pat_obj = self.data["patterns"][clean_pat]
        if is_win:
            pat_obj["wins"] += 1
        else:
            pat_obj["losses"] += 1
        pat_obj["net_pnl"] = round(pat_obj["net_pnl"] + profit_usd, 2)
        pat_tot = pat_obj["wins"] + pat_obj["losses"]
        pat_obj["win_rate"] = round((pat_obj["wins"] / pat_tot) * 100.0, 1)

        # Trade log entry
        self.data["trades"].append({
            "num": trade_num,
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "symbol": symbol,
            "pattern": clean_pat,
            "side": side,
            "stake": stake,
            "is_win": is_win,
            "profit": profit_usd,
            "balance": current_balance
        })

        self._save()

        # Check if milestone reached (every milestone_interval trades or end of 300)
        is_milestone = (trade_num % self.milestone_interval == 0) or (trade_num == self.target_trades)
        milestone_msg = None
        if is_milestone:
            milestone_msg = self.format_milestone_report(trade_num)

        return is_milestone, milestone_msg

    def format_milestone_report(self, trade_num: int) -> str:
        """Generates statistical milestone summary."""
        wins = self.data["wins"]
        losses = self.data["losses"]
        total = self.data["total_trades"]
        wr = round((wins / total) * 100.0, 2) if total > 0 else 0.0
        ci_lower, ci_upper = self.calculate_confidence_interval(wins, total, confidence=0.95)
        pnl = self.data["net_pnl"]
        max_dd = self.data["max_drawdown_usd"]
        max_dd_pct = self.data["max_drawdown_pct"]

        # Format per-pattern breakdown
        pattern_lines = []
        for pat, stats in sorted(self.data["patterns"].items(), key=lambda x: (x[1]["wins"] + x[1]["losses"]), reverse=True):
            p_tot = stats["wins"] + stats["losses"]
            p_wr = stats["win_rate"]
            p_pnl = stats["net_pnl"]
            icon = "🟢" if p_wr >= 54.0 else "🔴"
            pattern_lines.append(
                f"{icon} <b>{pat}:</b> {stats['wins']}W / {stats['losses']}L ({p_wr}% WR) | PnL: <b>${p_pnl:+,.2f}</b>"
            )

        pat_str = "\n".join(pattern_lines) if pattern_lines else "<i>Sin patrones suficientes aún.</i>"

        # Statistical evaluation against break-even (54.05%)
        if ci_lower >= 54.05:
            stat_verdict = "✅ <b>VENTAJA ESTADÍSTICA CONFIRMADA AL 95%</b> (Límite inferior > 54%)"
        elif wr >= 54.05 and ci_lower < 54.05:
            stat_verdict = "🟡 <b>EN ZONA POSITIVA PERO DENTRO DE MARGEN DE ERROR</b> (Continuar muestreo)"
        else:
            stat_verdict = "⚠️ <b>SIN VENTAJA ESTADÍSTICA DEMOSTRADA</b> (Por debajo del 54%)"

        pct_prog = round((total / self.target_trades) * 100.0, 1)
        bar_len = int(round(pct_prog / 10))
        bar = "🟩" * bar_len + "⬜" * (10 - bar_len)

        return (
            f"📊 <b>FORWARD-TEST HITO: {trade_num} / {self.target_trades} OPERACIONES</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Progreso del Ciclo:</b> {bar} <b>{pct_prog}%</b>\n\n"
            f"📈 <b>Tasa de Acierto (Win Rate):</b> <b>{wr}%</b>\n"
            f"🔬 <b>Intervalo Confianza (95% Wilson):</b> [<b>{ci_lower}%</b> — <b>{ci_upper}%</b>]\n"
            f"💰 <b>PnL Neto Acumulado:</b> <b>${pnl:+,.2f} USD</b>\n"
            f"📉 <b>Max Drawdown Observado:</b> ${max_dd:,.2f} ({max_dd_pct}%)\n"
            f"🛡 <b>Gestión:</b> Flat $25 USD (0.25%) | CERO Martingala\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>Diagnóstico Estadístico:</b>\n{stat_verdict}\n\n"
            f"📋 <b>DESGLOSE PATRÓN POR PATRÓN:</b>\n"
            f"{pat_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Forward-Testing científico 100% en tiempo real hacia adelante (Demo).</i>"
        )

    def get_summary(self) -> Dict[str, Any]:
        wins = self.data["wins"]
        total = self.data["total_trades"]
        wr = round((wins / total) * 100.0, 2) if total > 0 else 0.0
        ci_lower, ci_upper = self.calculate_confidence_interval(wins, total, confidence=0.95)
        return {
            "total_trades": total,
            "target_trades": self.target_trades,
            "wins": wins,
            "losses": self.data["losses"],
            "win_rate": wr,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "net_pnl": self.data["net_pnl"],
            "max_drawdown_usd": self.data["max_drawdown_usd"],
            "max_drawdown_pct": self.data["max_drawdown_pct"],
            "patterns": self.data["patterns"]
        }


forward_test_tracker = ForwardTestTracker(target_trades=300, milestone_interval=50)
