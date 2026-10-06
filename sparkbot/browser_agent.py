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


def _system_browser_executable():
    configured = os.getenv('SPARKBOT_BROWSER_EXECUTABLE', '').strip()
    candidates = [configured] if configured else []
    candidates += ['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser']
    for item in candidates:
        if item and Path(item).is_file(): return item
    return None

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
            launch_args = {"headless": os.getenv("SPARKBOT_BROWSER_HEADLESS", "1") != "0", "viewport": {"width": 1440, "height": 900}}
            executable = _system_browser_executable()
            if executable: launch_args["executable_path"] = executable
            self._context = self._playwright.chromium.launch_persistent_context(str(self.profile_dir), **launch_args)
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
        state["system_browser"] = _system_browser_executable()
        state["browser_mode"] = "system-browser" if state["system_browser"] else "playwright-managed"
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

    def click(self, selector: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not selector.strip():
            return {"ok": False, "error": "selector is required"}
        def op():
            try:
                page = self._page_or_start()
                locator = page.locator(selector).first
                label = ((locator.inner_text(timeout=3000) or "") + " " +
                         (locator.get_attribute("aria-label") or "")).strip()
                sensitive = ("publish", "publicar", "postar", "post", "share", "compartilhar",
                             "send", "enviar", "delete", "excluir", "follow", "seguir",
                             "comment", "comentar")
                if not confirmed and any(word in label.lower() for word in sensitive):
                    return {"ok": False, "approval_required": True, "selector": selector,
                            "label": label[:300], "error": "external side effect requires approval"}
                locator.click(timeout=15000)
                result = {"ok": True, "url": page.url, "selector": selector}
                self.monitor.record("click", url=page.url, target=selector, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("click", target=selector, status="error", details={"error": error})
                return {"ok": False, "error": error}
        return self._call(op)

    def fill(self, selector: str, value: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not selector.strip():
            return {"ok": False, "error": "selector is required"}
        def op():
            try:
                page = self._page_or_start()
                locator = page.locator(selector).first
                field_type = (locator.get_attribute("type") or "").lower()
                field_name = " ".join(filter(None, [
                    locator.get_attribute("name"),
                    locator.get_attribute("id"),
                    locator.get_attribute("placeholder"),
                    locator.get_attribute("aria-label"),
                ])).lower()
                if field_type == "password" or any(word in field_name for word in
                    ("password", "senha", "otp", "verification code", "código de verificação", "recovery code")):
                    return {"ok": False, "manual_required": True,
                            "error": "Sensitive authentication fields must be completed manually by the user."}
                locator.fill(value)
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
    def elements(self, limit: int = 80) -> dict[str, Any]:
        def op():
            try:
                page = self._page_or_start()
                items = page.locator("button, a, input, textarea, [contenteditable='true'], select").all()
                out = []
                for i, locator in enumerate(items[:max(1, min(limit, 150))]):
                    try:
                        out.append({
                            "index": i,
                            "tag": locator.evaluate("(el) => el.tagName.toLowerCase()"),
                            "text": (locator.inner_text(timeout=1000) or "")[:180],
                            "aria": locator.get_attribute("aria-label") or "",
                            "placeholder": locator.get_attribute("placeholder") or "",
                            "name": locator.get_attribute("name") or "",
                            "type": locator.get_attribute("type") or "",
                            "href": locator.get_attribute("href") or "",
                        })
                    except Exception:
                        continue
                return {"ok": True, "url": page.url, "title": page.title(), "elements": out}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return self._call(op)

    def upload(self, path: str) -> dict[str, Any]:
        if not path.strip():
            return {"ok": False, "error": "file path is required"}
        target = Path(path).expanduser().resolve()
        if not target.is_file():
            return {"ok": False, "error": "file does not exist"}
        def op():
            try:
                page = self._page_or_start()
                inputs = page.locator("input[type='file']")
                if inputs.count() == 0:
                    return {"ok": False, "error": "No file input is visible on the current page."}
                inputs.first.set_input_files(str(target))
                result = {"ok": True, "url": page.url, "filename": target.name, "size": target.stat().st_size}
                self.monitor.record("upload", url=page.url, status="success", details=result)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.monitor.record("upload", url=getattr(self._page, "url", ""), status="error",
                                    details={"error": error})
                return {"ok": False, "error": error}
        return self._call(op)

    def fill_best_textbox(self, value: str) -> dict[str, Any]:
        def op():
            try:
                page = self._page_or_start()
                candidates = page.locator("textarea, [contenteditable='true'], [role='textbox']")
                count = candidates.count()
                if count == 0:
                    return {"ok": False, "error": "No editable text box found."}
                for i in range(count):
                    locator = candidates.nth(i)
                    try:
                        if locator.is_visible():
                            field_type = (locator.get_attribute("type") or "").lower()
                            if field_type != "password":
                                locator.fill(value)
                                result = {"ok": True, "url": page.url, "index": i, "value_length": len(value)}
                                self.monitor.record("fill", url=page.url, target=f"textbox:{i}",
                                                    status="success", details=result)
                                return result
                    except Exception:
                        continue
                return {"ok": False, "error": "No visible editable text box found."}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return self._call(op)

    def click_publish(self, *, confirmed: bool = False) -> dict[str, Any]:
        def op():
            try:
                page = self._page_or_start()
                pattern = r"(?i)^(publish|publicar|post|postar|share|compartilhar|tweet|send|enviar)$"
                locator = page.get_by_role("button", name=__import__("re").compile(pattern)).first
                if locator.count() == 0:
                    return {"ok": False, "error": "No publish/share button found."}
                label = (locator.inner_text(timeout=2000) or "").strip()
                if not confirmed:
                    return {"ok": False, "approval_required": True, "label": label,
                            "error": "publishing requires approval"}
                locator.click(timeout=15000)
                result = {"ok": True, "url": page.url, "label": label}
                self.monitor.record("publish", url=page.url, target=label,
                                    status="success", details=result)
                return result
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return self._call(op)
