from __future__ import annotations

"""Optional real browser runtime powered by Playwright.

The browser is intentionally conservative: only public HTTP(S) destinations are allowed,
navigation/actions are audited, and authentication/CAPTCHA bypass is never attempted.
"""

import ipaddress
import os
import socket
import threading
import urllib.parse
from pathlib import Path
from typing import Any

from .browser_monitor import BrowserMonitor


def _public_url(url: str) -> tuple[bool, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "Only public HTTP/HTTPS URLs are allowed."
    try:
        addresses = {x[4][0] for x in socket.getaddrinfo(parsed.hostname, None)}
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False, "Private/local network targets are blocked."
    except OSError as exc:
        return False, f"DNS resolution failed: {exc}"
    return True, ""


class BrowserAgent:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._playwright = None
        self._context = None
        self._page = None
        self._started = False
        self._error = ""
        self.monitor = BrowserMonitor()
        self.profile_dir = Path(
            os.getenv("SPARKBOT_BROWSER_PROFILE", ".sparkbot-browser")
        ).expanduser().resolve()

    def status(self) -> dict[str, Any]:
        with self._lock:
            installed = False
            try:
                import playwright  # noqa: F401
                installed = True
            except ImportError:
                pass
            return {
                "installed": installed,
                "started": self._started,
                "page": bool(self._page),
                "url": self._page.url if self._page else "",
                "title": self._page.title() if self._page else "",
                "error": self._error,
                "profile_dir": str(self.profile_dir),
            }

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._started:
                return self.status()
            try:
                from playwright.sync_api import sync_playwright
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                self._playwright = sync_playwright().start()
                self._context = self._playwright.chromium.launch_persistent_context(
                    str(self.profile_dir),
                    headless=os.getenv("SPARKBOT_BROWSER_HEADLESS", "1") != "0",
                    viewport={"width": 1440, "height": 900},
                )
                self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
                self._started = True
                self._error = ""
                self.monitor.record("browser_started", status="success")
                return self.status()
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                self._started = False
                self.monitor.record("browser_start_failed", status="error", details={"error": self._error})
                return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            try:
                if self._context:
                    self._context.close()
                if self._playwright:
                    self._playwright.stop()
            finally:
                self._context = self._page = self._playwright = None
                self._started = False
            self.monitor.record("browser_stopped", status="success")
            return self.status()

    def _require_page(self):
        if not self._started or not self._page:
            result = self.start()
            if not result["started"]:
                raise RuntimeError(result["error"] or "Browser runtime unavailable")
        return self._page

    def navigate(self, url: str) -> dict[str, Any]:
        ok, reason = _public_url(url)
        if not ok:
            self.monitor.record("navigate_blocked", url=url, status="blocked", details={"reason": reason})
            return {"ok": False, "error": reason}
        with self._lock:
            try:
                page = self._require_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                result = {
                    "ok": True,
                    "url": page.url,
                    "title": page.title(),
                    "status": response.status if response else None,
                }
                self.monitor.record("navigate", url=page.url, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("navigate", url=url, status="error", details={"error": error})
                return {"ok": False, "error": error}

    def click(self, selector: str, *, approval: bool = False) -> dict[str, Any]:
        if not selector.strip():
            return {"ok": False, "error": "selector is required"}
        with self._lock:
            try:
                page = self._require_page()
                page.locator(selector).first.click(timeout=15000)
                result = {"ok": True, "url": page.url, "selector": selector}
                self.monitor.record("click", url=page.url, target=selector, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("click", url=self._page.url if self._page else "", target=selector, status="error", details={"error": error})
                return {"ok": False, "error": error}

    def fill(self, selector: str, value: str, *, approval: bool = False) -> dict[str, Any]:
        if not selector.strip():
            return {"ok": False, "error": "selector is required"}
        with self._lock:
            try:
                page = self._require_page()
                page.locator(selector).first.fill(value)
                result = {"ok": True, "url": page.url, "selector": selector, "value_length": len(value)}
                self.monitor.record("fill", url=page.url, target=selector, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("fill", url=self._page.url if self._page else "", target=selector, status="error", details={"error": error})
                return {"ok": False, "error": error}

    def screenshot(self) -> dict[str, Any]:
        with self._lock:
            try:
                page = self._require_page()
                target = Path("data/browser-screenshots")
                target.mkdir(parents=True, exist_ok=True)
                filename = target / f"{__import__('time').strftime('%Y%m%d-%H%M%S')}.png"
                page.screenshot(path=str(filename), full_page=True)
                result = {"ok": True, "path": str(filename), "url": page.url}
                self.monitor.record("screenshot", url=page.url, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("screenshot", status="error", details={"error": error})
                return {"ok": False, "error": error}

    def text(self, max_chars: int = 12000) -> dict[str, Any]:
        with self._lock:
            try:
                page = self._require_page()
                value = page.locator("body").inner_text(timeout=10000)
                return {"ok": True, "url": page.url, "title": page.title(), "text": value[:max(1000, min(max_chars, 20000))]}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
