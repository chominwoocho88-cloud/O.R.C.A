"""Reusable test fixtures for time, filesystem, sqlite, env, and network stubs.

These helpers intentionally stay lightweight and stdlib-only so future tests
can reuse them without pulling in external fixture libraries.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sqlite3
import sys
import tempfile
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


def _build_frozen_datetime(frozen: datetime):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return frozen if frozen.tzinfo is None else frozen.replace(tzinfo=None)
            if frozen.tzinfo is None:
                return frozen.replace(tzinfo=tz)
            return frozen.astimezone(tz)

        @classmethod
        def utcnow(cls):
            if frozen.tzinfo is None:
                return frozen
            return frozen.astimezone(timezone.utc).replace(tzinfo=None)

    return FrozenDateTime


@contextlib.contextmanager
def freeze_time(iso_str: str, *, datetime_targets: list[str] | tuple[str, ...] | None = None):
    """Freeze ``time.time()`` and optionally module-level ``datetime.now()`` lookups.

    Example:
        with freeze_time(
            "2026-04-22T10:00:00+09:00",
            datetime_targets=["tests.test_fixtures.datetime"],
        ):
            ...
    """

    frozen = datetime.fromisoformat(iso_str)
    timestamp = frozen.timestamp()
    frozen_datetime = _build_frozen_datetime(frozen)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("time.time", return_value=timestamp))
        stack.enter_context(patch("datetime.datetime", frozen_datetime))
        for target in datetime_targets or ():
            stack.enter_context(patch(target, frozen_datetime))
        yield frozen


@contextlib.contextmanager
def isolated_filesystem():
    """Create a temporary working directory and restore the previous cwd on exit.

    Example:
        with isolated_filesystem() as tmpdir:
            Path("sample.json").write_text("{}")
    """

    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        temp_path = Path(tmpdir)
        os.chdir(temp_path)
        try:
            yield temp_path
        finally:
            os.chdir(original_cwd)


def _patch_module_attributes(module_name: str, stub_module: types.ModuleType, attrs: dict[str, object]):
    stack = contextlib.ExitStack()
    existing_module = sys.modules.get(module_name)
    if existing_module is not None:
        for attr_name, value in attrs.items():
            if hasattr(existing_module, attr_name):
                stack.enter_context(patch.object(existing_module, attr_name, value))
    stack.enter_context(patch.dict(sys.modules, {module_name: stub_module}))
    return stack


def _load_state_module():
    return importlib.import_module("orca.state")


def _seed_in_memory_db(kind: str):
    state = _load_state_module()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        state_db = Path(tmpdir) / "orca_state.db"
        jackal_db = Path(tmpdir) / "jackal_state.db"
        with patch.object(state, "STATE_DB_FILE", state_db), patch.object(state, "JACKAL_DB_FILE", jackal_db):
            state.init_state_db()
            source_path = state_db if kind == "orca" else jackal_db
            source_conn = sqlite3.connect(source_path)
            memory_conn = sqlite3.connect(":memory:")
            memory_conn.row_factory = sqlite3.Row
            memory_conn.execute("PRAGMA foreign_keys = ON")
            try:
                source_conn.backup(memory_conn)
            finally:
                source_conn.close()
    return memory_conn


@contextlib.contextmanager
def in_memory_orca_db():
    """Yield an in-memory sqlite connection seeded with the current ORCA schema.

    Example:
        with in_memory_orca_db() as conn:
            conn.execute("SELECT COUNT(*) FROM runs")
    """

    connection = _seed_in_memory_db("orca")
    try:
        yield connection
    finally:
        connection.close()


@contextlib.contextmanager
def in_memory_jackal_db():
    """Yield an in-memory sqlite connection seeded with the current JACKAL schema.

    Example:
        with in_memory_jackal_db() as conn:
            conn.execute("SELECT COUNT(*) FROM jackal_live_events")
    """

    connection = _seed_in_memory_db("jackal")
    try:
        yield connection
    finally:
        connection.close()


@contextlib.contextmanager
def env_overrides(**kwargs: str | None):
    """Temporarily override environment variables.

    Example:
        with env_overrides(TELEGRAM_TOKEN="token", TELEGRAM_CHAT_ID="123"):
            ...
    """

    sentinel = object()
    previous = {key: os.environ.get(key, sentinel) for key in kwargs}
    for key, value in kwargs.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextlib.contextmanager
def mock_anthropic(response: str = "default response"):
    """Stub ``anthropic.Anthropic`` and capture ``messages.create`` calls.

    Example:
        with mock_anthropic("analysis result") as calls:
            import anthropic
            anthropic.Anthropic().messages.create(model="x", messages=[])
    """

    calls: list[dict[str, object]] = []
    anthropic = types.ModuleType("anthropic")

    class DummyBlock:
        def __init__(self, text: str):
            self.text = text

    class DummyResponse:
        def __init__(self, text: str):
            self.content = [DummyBlock(text)]

    class DummyMessages:
        def create(self, *args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            return DummyResponse(response)

    class DummyAnthropic:
        def __init__(self, api_key=None, **kwargs):
            self.api_key = api_key
            self.kwargs = kwargs
            self.messages = DummyMessages()

    anthropic.Anthropic = DummyAnthropic

    with _patch_module_attributes("anthropic", anthropic, {"Anthropic": DummyAnthropic}):
        yield calls


@contextlib.contextmanager
def mock_yfinance(data: dict | None = None):
    """Stub ``yfinance.Ticker`` and ``yfinance.download`` with simple payloads.

    Example:
        with mock_yfinance({"AAPL": {"history": [1, 2, 3]}}) as calls:
            import yfinance as yf
            yf.Ticker("AAPL").history(period="5d")
    """

    payload = data or {}
    calls = {"ticker": [], "download": []}
    yfinance = types.ModuleType("yfinance")

    class DummyTicker:
        def __init__(self, ticker: str):
            self.ticker = ticker

        @property
        def options(self):
            ticker_payload = payload.get(self.ticker, {})
            if isinstance(ticker_payload, dict):
                return list(ticker_payload.get("options", []))
            return []

        def history(self, *args, **kwargs):
            calls["ticker"].append({"ticker": self.ticker, "args": args, "kwargs": kwargs})
            ticker_payload = payload.get(self.ticker, {})
            if isinstance(ticker_payload, dict) and "history" in ticker_payload:
                return ticker_payload["history"]
            return ticker_payload

        def option_chain(self, expiry):
            ticker_payload = payload.get(self.ticker, {})
            if isinstance(ticker_payload, dict) and "option_chain" in ticker_payload:
                return ticker_payload["option_chain"]
            return types.SimpleNamespace(calls=[], puts=[])

    def download(*args, **kwargs):
        calls["download"].append({"args": args, "kwargs": kwargs})
        return payload.get("__download__")

    yfinance.Ticker = DummyTicker
    yfinance.download = download

    with _patch_module_attributes("yfinance", yfinance, {"Ticker": DummyTicker, "download": download}):
        yield calls


@contextlib.contextmanager
def mock_telegram(success: bool = True):
    """Stub Telegram delivery through ``httpx.post`` and capture payloads.

    Example:
        with mock_telegram(success=True) as calls:
            import orca.notify_transport as notify_transport
            notify_transport.send_message("hello")
    """

    calls: list[dict[str, object]] = []
    httpx = types.ModuleType("httpx")

    class DummyResponse:
        def json(self):
            return {"ok": success}

        def raise_for_status(self):
            return None

    def post(url, *args, **kwargs):
        calls.append({"url": url, "args": args, "kwargs": kwargs})
        return DummyResponse()

    def get(*args, **kwargs):
        return DummyResponse()

    httpx.post = post
    httpx.get = get

    with _patch_module_attributes("httpx", httpx, {"post": post, "get": get}):
        yield calls
