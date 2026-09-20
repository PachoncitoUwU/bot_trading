"""Windows Power Management utilities to keep the bot running 24/7 without PC sleep."""
import ctypes
import sys
from app.core.logger import logger


# Windows Execution State Flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def enable_24_7_execution_mode() -> bool:
    """
    Prevents Windows from entering Sleep / Standby mode while the trading bot is active.
    Allows the screen/monitor to turn off safely to save electricity and screen life,
    while keeping the CPU, RAM, and Network active 24/7.
    """
    if sys.platform == "win32":
        try:
            # Tell Windows Kernel this process requires continuous execution
            result = ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            )
            if result != 0:
                logger.info(
                    "[POWER] 🛡️ Modo 24/7 Activado: Windows tiene prohibido suspender el PC mientras el bot esté operando (la pantalla puede apagarse para ahorrar energía)."
                )
                return True
            else:
                logger.warning("[POWER] SetThreadExecutionState returned 0.")
        except Exception as e:
            logger.warning(f"[POWER] No se pudo invocar SetThreadExecutionState: {e}")
    return False


def disable_24_7_execution_mode() -> None:
    """Restores standard Windows power behavior upon bot shutdown."""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            logger.info("[POWER] Modo 24/7 Desactivado: Restaurado el comportamiento estándar de energía de Windows.")
        except Exception as e:
            logger.debug(f"[POWER] Error restaurando estado de energía: {e}")
