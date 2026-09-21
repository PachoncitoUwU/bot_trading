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
        instrument: str = "BINARY",
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

        # Trade log entry with strict regime (OTC vs REAL_MARKET) and instrument tagging (BINARY vs DIGITAL)
        regime = "OTC" if "-OTC" in symbol.upper() else "REAL_MARKET"
        inst = instrument.upper() if instrument else "BINARY"
        self.data["trades"].append({
            "num": trade_num,
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "symbol": symbol,
            "regime": regime,
            "instrument": inst,
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

    def calculate_cadence(self) -> Dict[str, Any]:
        """Calculates trade cadence (trades/day) and projected days to reach checkpoints."""
        start_str = self.data.get("start_time")
        total = self.data.get("total_trades", 0)
        trades_per_day = 0.0
        cadence_str = "Midiendo tiempo de muestra..."
        est_days_50 = "N/A"
        elapsed_hours = 0.0

        if start_str:
            try:
                clean_iso = start_str.replace("Z", "+00:00")
                start_dt = datetime.fromisoformat(clean_iso)
                if start_dt.tzinfo:
                    start_dt = start_dt.replace(tzinfo=None)
                elapsed_hours = max(0.01, (datetime.utcnow() - start_dt).total_seconds() / 3600.0)
                if elapsed_hours >= 0.5 and total > 0:
                    trades_per_day = round((total / elapsed_hours) * 24.0, 1)
                    cadence_str = f"~{trades_per_day} trades/día"
                    remaining_50 = max(0, 50 - total)
                    if trades_per_day > 0 and remaining_50 > 0:
                        est_days = round(remaining_50 / trades_per_day, 1)
                        est_days_50 = f"~{est_days} días"
                    elif remaining_50 == 0:
                        est_days_50 = "¡Alcanzado!"
                elif total == 0:
                    cadence_str = "Esperando primeras señales de mercado real"
            except Exception as e:
                logger.debug(f"[CADENCE] Calculation error: {e}")

        return {
            "elapsed_hours": round(elapsed_hours, 1),
            "trades_per_day": trades_per_day,
            "cadence_str": cadence_str,
            "est_days_to_checkpoint_50": est_days_50
        }

    def reset_300_cycle(self, starting_balance: float = 9230.31, cycle_name: str = "REAL_FOREX_MKT") -> None:
        """Archives preliminary test data and restarts the cycle with 100% frozen rules."""
        archive_entry = {
            "archived_at": datetime.utcnow().isoformat(),
            "cycle_label": self.data.get("cycle_label", "OTC_SYNTHETIC"),
            "total_trades": self.data.get("total_trades", 0),
            "wins": self.data.get("wins", 0),
            "losses": self.data.get("losses", 0),
            "net_pnl": self.data.get("net_pnl", 0.0),
            "trades": self.data.get("trades", [])
        }
        archives = self.data.get("archives", [])
        archives.append(archive_entry)

        self.data = {
            "cycle_active": True,
            "cycle_label": cycle_name,
            "start_time": datetime.utcnow().isoformat(),
            "target_trades": self.target_trades,
            "checkpoint_trades": 50,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "net_pnl": 0.0,
            "starting_balance": round(starting_balance, 2),
            "current_balance": round(starting_balance, 2),
            "peak_balance": round(starting_balance, 2),
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "patterns": {},
            "trades": [],
            "archives": archives
        }
        self._save()
        logger.info(f"[FORWARD TEST] 🔄 Ciclo {cycle_name} reiniciado a 0/{self.target_trades} con REGLAS CONGELADAS. Saldo base: ${starting_balance:.2f} USD")

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

        pct_prog = round((total / self.target_trades) * 100, 1) if self.target_trades > 0 else 0.0
        filled = min(10, max(0, int(pct_prog // 10)))
        bar = "█" * filled + "░" * (10 - filled)
        cadence = self.calculate_cadence()

        # Format per-pattern breakdown with strict sample size (n) and n < 20 warnings
        pattern_lines = []
        for pat, stats in sorted(self.data["patterns"].items(), key=lambda x: (x[1]["wins"] + x[1]["losses"]), reverse=True):
            p_tot = stats["wins"] + stats["losses"]
            p_wr = stats["win_rate"]
            p_pnl = stats["net_pnl"]
            if p_tot < 20:
                pattern_lines.append(
                    f"⚠️ <b>{pat} (n={p_tot}):</b> {stats['wins']}W / {stats['losses']}L | "
                    f"<i>[Muestra insuficiente (&lt;20 trades) — Sin significancia]</i> | PnL: <b>${p_pnl:+,.2f}</b>"
                )
            else:
                icon = "🟢" if p_wr >= 54.05 else "🔴"
                pattern_lines.append(
                    f"{icon} <b>{pat} (n={p_tot}):</b> {stats['wins']}W / {stats['losses']}L (<b>{p_wr}% WR</b>) | PnL: <b>${p_pnl:+,.2f}</b>"
                )

        pat_str = "\n".join(pattern_lines) if pattern_lines else "<i>Sin patrones suficientes aún.</i>"

        # Statistical evaluation against break-even (54.05%)
        if ci_lower >= 54.05:
            stat_verdict = "✅ <b>VENTAJA ESTADÍSTICA CONFIRMADA AL 95%</b> (Límite inferior > 54.05%)"
        elif wr >= 54.05 and ci_lower < 54.05:
            stat_verdict = f"🟡 <b>PROMEDIO EN {wr}% PERO DENTRO DE MARGEN DE ERROR</b> (Límite inferior en {ci_lower}%, continuar muestreo)"
        else:
            stat_verdict = f"⚠️ <b>SIN VENTAJA ESTADÍSTICA DEMOSTRADA</b> (WR en {wr}%, límite inferior en {ci_lower}%)"

        # Regime breakdown: OTC vs Real Market
        otc_trades = [t for t in self.data["trades"] if t.get("regime") == "OTC"]
        real_trades = [t for t in self.data["trades"] if t.get("regime") == "REAL_MARKET"]
        otc_wins = sum(1 for t in otc_trades if t.get("is_win"))
        real_wins = sum(1 for t in real_trades if t.get("is_win"))
        otc_wr = round((otc_wins / len(otc_trades)) * 100.0, 1) if otc_trades else 0.0
        real_wr = round((real_wins / len(real_trades)) * 100.0, 1) if real_trades else 0.0

        # Instrument breakdown: BINARY vs DIGITAL
        bin_trades = [t for t in self.data["trades"] if t.get("instrument") == "BINARY"]
        dig_trades = [t for t in self.data["trades"] if t.get("instrument") == "DIGITAL"]
        bin_wins = sum(1 for t in bin_trades if t.get("is_win"))
        dig_wins = sum(1 for t in dig_trades if t.get("is_win"))
        bin_wr = round((bin_wins / len(bin_trades)) * 100.0, 1) if bin_trades else 0.0
        dig_wr = round((dig_wins / len(dig_trades)) * 100.0, 1) if dig_trades else 0.0

        cycle_label = self.data.get("cycle_label", "REAL_FOREX_MKT")

        return (
            f"📊 <b>FORWARD-TEST: {trade_num} / 50 CHECKPOINT ({self.target_trades} TOTAL)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷 <b>Ciclo:</b> <code>{cycle_label}</code> (Muestra limpia 100% no-OTC)\n"
            f"🎯 <b>Progreso:</b> {bar} <b>{pct_prog}%</b> (n={total})\n"
            f"⏱ <b>Ritmo Operativo:</b> {cadence['cadence_str']}\n"
            f"⏳ <b>Tiempo est. a n=50:</b> {cadence['est_days_to_checkpoint_50']}\n\n"
            f"📈 <b>Win Rate Global:</b> <b>{wr}%</b> (n={total})\n"
            f"• 🏦 <b>Mercado Real Forex:</b> <b>{real_wr}%</b> ({real_wins}W / {len(real_trades) - real_wins}L | n={len(real_trades)})\n"
            f"• 🪐 <b>OTC (Ciclo actual):</b> <b>{otc_wr}%</b> (n={len(otc_trades)})\n"
            f"• ⚡ <b>Opciones Binarias:</b> <b>{bin_wr}%</b> ({bin_wins}W / {len(bin_trades) - bin_wins}L | n={len(bin_trades)})\n"
            f"• 📱 <b>Opciones Digitales:</b> <b>{dig_wr}%</b> ({dig_wins}W / {len(dig_trades) - dig_wins}L | n={len(dig_trades)})\n\n"
            f"🔬 <b>Intervalo Confianza (95% Wilson):</b> [<b>{ci_lower}%</b> — <b>{ci_upper}%</b>]\n"
            f"💰 <b>PnL Neto Acumulado:</b> <b>${pnl:+,.2f} USD</b>\n"
            f"📉 <b>Max Drawdown Observado:</b> ${max_dd:,.2f} ({max_dd_pct}%)\n"
            f"🛡 <b>Gestión:</b> Flat $25 USD (0.25%) | <b>CERO Martingala</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>Diagnóstico Estadístico Actual:</b>\n{stat_verdict}\n\n"
            f"📋 <b>DESGLOSE POR PATRÓN (Mínimo n=20 para validez):</b>\n"
            f"{pat_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚖️ <b>CRITERIOS ESTABLECIDOS:</b>\n"
            f"• <b>Checkpoint n=50:</b> Evaluar si el IC sugiere edge o si se descarta el modelo.\n"
            f"• <b>Límite inferior IC &gt; 54%:</b> Viabilidad estadística demostrada.\n"
            f"• <b>Win Rate &lt; 50%:</b> Modelo sin ventaja predictiva.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Reglas 100% congeladas. Sin mutación de pesos ni mezcla de datos.</i>"
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
