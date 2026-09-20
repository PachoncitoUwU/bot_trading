"""Lightweight Telegram Bot API HTTP client using httpx.

Sends messages via the Telegram Bot API without heavy framework dependencies.
Uses httpx.AsyncClient (already a transitive FastAPI dependency).
"""
import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logger import logger

_BASE_URL = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    """Async Telegram Bot API client for sending messages and answering callbacks."""

    def __init__(self, token: str):
        self._token = token
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    def _url(self, method: str) -> str:
        return _BASE_URL.format(token=self._token, method=method)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Sends a message to a chat. Returns the message dict or None on failure."""
        if not self._token or not chat_id:
            return None

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            client = await self._get_client()
            resp = await client.post(self._url("sendMessage"), json=payload)
            resp.raise_for_status()
            return resp.json().get("result")
        except httpx.HTTPStatusError as e:
            logger.error(f"[TELEGRAM] sendMessage HTTP error: {e.response.status_code} — {e.response.text}")
        except Exception as e:
            logger.error(f"[TELEGRAM] sendMessage failed: {e}")
        return None

    async def send_photo(
        self,
        chat_id: str,
        photo_bytes: Any,
        caption: Optional[str] = None,
        parse_mode: str = "HTML"
    ) -> Optional[Dict[str, Any]]:
        """Sends a photo/image directly to Telegram."""
        if not self._token or not chat_id:
            return None

        try:
            client = await self._get_client()
            files = {"photo": ("trade_result.png", photo_bytes, "image/png")}
            data = {"chat_id": chat_id, "parse_mode": parse_mode}
            if caption:
                data["caption"] = caption

            resp = await client.post(self._url("sendPhoto"), data=data, files=files)
            resp.raise_for_status()
            return resp.json().get("result")
        except Exception as e:
            logger.error(f"[TELEGRAM] sendPhoto failed: {e}")
            return None

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
    ) -> bool:
        """Acknowledges an inline button press to dismiss the loading spinner."""
        try:
            client = await self._get_client()
            resp = await client.post(
                self._url("answerCallbackQuery"),
                json={"callback_query_id": callback_query_id, "text": text},
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"[TELEGRAM] answerCallbackQuery failed: {e}")
            return False

    async def get_updates(
        self,
        offset: int = 0,
        timeout: int = 30,
        allowed_updates: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Long-polls for new updates. Returns list of update dicts."""
        params: Dict[str, Any] = {"offset": offset, "timeout": timeout}
        if allowed_updates is not None:
            params["allowed_updates"] = allowed_updates

        try:
            client = await self._get_client()
            resp = await client.get(
                self._url("getUpdates"),
                params=params,
                timeout=timeout + 5.0,  # httpx timeout must exceed Telegram's
            )
            resp.raise_for_status()
            return resp.json().get("result", [])
        except httpx.ReadTimeout:
            # Normal for long-polling — no updates in the window
            return []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                logger.warning("[TELEGRAM] 409 Conflict en getUpdates. Esperando 5s para liberar sesión previa...")
                await asyncio.sleep(5)
            else:
                logger.error(f"[TELEGRAM] getUpdates HTTP {e.response.status_code}: {e}")
                await asyncio.sleep(2)
            return []
        except Exception as e:
            logger.error(f"[TELEGRAM] getUpdates failed: {e}")
            await asyncio.sleep(2)
            return []

    async def close(self) -> None:
        """Closes the underlying HTTP session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("[TELEGRAM] HTTP client closed.")


# Singleton — instantiated in main.py lifespan if token is configured
telegram_client: Optional[TelegramClient] = None


def get_telegram_client() -> Optional[TelegramClient]:
    """Returns the global TelegramClient instance, or None if unconfigured."""
    return telegram_client


def init_telegram_client() -> Optional[TelegramClient]:
    """Initializes the global TelegramClient from settings. Returns None if no token."""
    global telegram_client
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("[TELEGRAM] TELEGRAM_BOT_TOKEN not set — Telegram integration disabled.")
        return None
    telegram_client = TelegramClient(token=settings.TELEGRAM_BOT_TOKEN)
    logger.info("[TELEGRAM] TelegramClient initialized.")
    return telegram_client
