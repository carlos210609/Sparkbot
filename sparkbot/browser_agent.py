from __future__ import annotations

"""Optional real browser runtime powered by Playwright.

All Playwright calls are serialized through one dedicated worker thread because the
synchronous Playwright API is thread-affine.
"""

import concurrent.futures
import ipaddress
import os
import socket
import urllib.parse
from pathlib import Path
from typing import Any, Callable

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
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="sparkbot-browser")
        self._playwright = None
        self._context = None
        self._page = None
        self._started = False
        self._error = ""
        self._state_lock = __import__("threading").RLock()
        self.monitor = BrowserMonitor()
        self.profile_dir = Path(os.getenv("SPARKBOT_BROWSER_PROFILE", ".sparkbot-browser")).expanduser().resolve()

    def _call(self, fn: Callable[..., Any], *args: Any) -> Any:
        return self._executor.submit(fn, *args).result(timeout=60)

    def _start_impl(self) -> dict[str, Any]:
        if self._started:
            return self._status_state()
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
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            self._started = False
            self.monitor.record("browser_start_failed", status="error", details={"error": self._error})
        return self._status_state()

    def _status_state(self) -> dict[str, Any]:
        url = ""
        title = ""
        if self._page:
            try:
                url = self._page.url
                title = self._page.title()
            except Exception:
                pass
        return {
            "started": self._started,
            "page": bool(self._page),
            "url": url,
            "title": title,
            "error": self._error,
            "profile_dir": str(self.profile_dir),
        }

    def status(self) -> dict[str, Any]:
        installed = False
        try:
            import playwright  # noqa: F401
            installed = True
        except ImportError:
            pass
        with self._state_lock:
            state = self._call(self._status_state)
        state["installed"] = installed
        return state

    def start(self) -> dict[str, Any]:
        with self._state_lock:
            return self._call(self._start_impl)

    def _stop_impl(self) -> dict[str, Any]:
        try:
            if self._context:
                self._context.close()
            if self._playwright:
                self._playwright.stop()
        finally:
            self._context = self._page = self._playwright = None
            self._started = False
        self.monitor.record("browser_stopped", status="success")
        return self._status_state()

    def stop(self) -> dict[str, Any]:
        with self._state_lock:
            return self._call(self._stop_impl)

    def _page_or_start(self):
        if not self._started:
            self._start_impl()
        if not self._page:
            raise RuntimeError(self._error or "Browser runtime unavailable")
        return self._page

    def navigate(self, url: str) -> dict[str, Any]:
        ok, reason = _public_url(url)
        if not ok:
            self.monitor.record("navigate_blocked", url=url, status="blocked", details={"reason": reason})
            return {"ok": False, "error": reason}

        def op():
            try:
                page = self._page_or_start()
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                final_ok, final_reason = _public_url(page.url)
                if not final_ok:
                    page.goto("about:blank")
                    self.monitor.record("navigate_blocked", url=url, status="blocked", details={"reason": final_reason})
                    return {"ok": False, "error": final_reason}
                result = {"ok": True, "url": page.url, "title": page.title(), "status": response.status if response else None}
                self.monitor.record("navigate", url=page.url, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("navigate", url=url, status="error", details={"error": error})
                return {"ok": False, "error": error}
        return self._call(op)

    def click(self, selector: str) -> dict[str, Any]:
        if not selector.strip():
            return {"ok": False, "error": "selector is required"}
        def op():
            try:
                page = self._page_or_start()
                page.locator(selector).first.click(timeout=15000)
                result = {"ok": True, "url": page.url, "selector": selector}
                self.monitor.record("click", url=page.url, target=selector, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("click", target=selector, status="error", details={"error": error})
                return {"ok": False, "error": error}
        return self._call(op)

    def fill(self, selector: str, value: str) -> dict[str, Any]:
        if not selector.strip():
            return {"ok": False, "error": "selector is required"}
        def op():
            try:
                page = self._page_or_start()
                page.locator(selector).first.fill(value)
                result = {"ok": True, "url": page.url, "selector": selector, "value_length": len(value)}
                self.monitor.record("fill", url=page.url, target=selector, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("fill", target=selector, status="error", details={"error": error})
                return {"ok": False, "error": error}
        return self._call(op)

    def screenshot(self) -> dict[str, Any]:
        def op():
            try:
                page = self._page_or_start()
                target = Path("data/browser-screenshots")
                target.mkdir(parents=True, exist_ok=True)
                filename = target / f"{__import__('time').strftime('%Y%m%d-%H%M%S-%f')}.png"
                page.screenshot(path=str(filename), full_page=True)
                result = {"ok": True, "path": str(filename), "url": page.url}
                self.monitor.record("screenshot", url=page.url, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("screenshot", status="error", details={"error": error})
                return {"ok": False, "error": error}
        return self._call(op)

    def text(self, max_chars: int = 12000) -> dict[str, Any]:
        def op():
            try:
                page = self._page_or_start()
                value = page.locator("body").inner_text(timeout=10000)
                return {"ok": True, "url": page.url, "title": page.title(), "text": value[:max(1000, min(max_chars, 20000))]}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return self._call(op)
