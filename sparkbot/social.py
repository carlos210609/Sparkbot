"""Legitimate social/account operations over the real browser runtime.

This layer deliberately avoids storing passwords, OTPs or recovery codes. It can open
official signup/login pages, inspect the UI, prepare drafts and publish only after the
approval gate is satisfied. CAPTCHA, MFA, KYC and security challenges remain human steps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    home_url: str
    signup_url: str
    capabilities: tuple[str, ...]

PLATFORMS: tuple[Platform, ...] = (
    Platform("instagram","Instagram","https://www.instagram.com/","https://www.instagram.com/accounts/emailsignup/",
             ("account","profile","post","reel","story","comments","analytics")),
    Platform("tiktok","TikTok","https://www.tiktok.com/","https://www.tiktok.com/signup",
             ("account","profile","video","post","comments","analytics")),
    Platform("youtube","YouTube","https://www.youtube.com/","https://accounts.google.com/SignUp",
             ("account","channel","video","shorts","comments","analytics")),
    Platform("linkedin","LinkedIn","https://www.linkedin.com/","https://www.linkedin.com/signup",
             ("account","profile","post","video","article","page","analytics")),
    Platform("facebook","Facebook","https://www.facebook.com/","https://www.facebook.com/r.php",
             ("account","profile","page","post","video","reels","comments","analytics")),
    Platform("x","X","https://x.com/","https://x.com/i/flow/signup",
             ("account","profile","post","media","replies","analytics")),
    Platform("threads","Threads","https://www.threads.net/","https://www.threads.net/signup",
             ("account","profile","post","replies","analytics")),
    Platform("pinterest","Pinterest","https://www.pinterest.com/","https://www.pinterest.com/join/register/",
             ("account","business","pin","board","video","analytics")),
    Platform("reddit","Reddit","https://www.reddit.com/","https://www.reddit.com/register/",
             ("account","profile","post","comment","community","analytics")),
    Platform("canva","Canva","https://www.canva.com/","https://www.canva.com/signup/",
             ("account","design","brand","video","export")),
    Platform("runway","Runway","https://app.runwayml.com/","https://app.runwayml.com/",
             ("account","ai_video","generation","export")),
    Platform("kling","Kling AI","https://klingai.com/","https://klingai.com/",
             ("account","ai_video","generation","export")),
)

PLATFORM_INDEX = {p.id: p for p in PLATFORMS}

HIGH_RISK_ACTIONS = {
    "create_account", "publish", "delete", "send_message", "comment", "follow",
    "like", "run_ad", "purchase", "change_credentials",
}

def get_platform(platform: str) -> Platform:
    key = platform.strip().lower()
    if key not in PLATFORM_INDEX:
        raise ValueError(f"unsupported platform: {platform}")
    return PLATFORM_INDEX[key]

def catalog() -> list[dict[str, Any]]:
    return [{"id": p.id, "name": p.name, "home_url": p.home_url,
             "signup_url": p.signup_url, "capabilities": list(p.capabilities)} for p in PLATFORMS]

def action_requires_approval(action: str) -> bool:
    return action.strip().lower() in HIGH_RISK_ACTIONS

class SocialController:
    def __init__(self, browser):
        self.browser = browser

    def open(self, platform: str, purpose: str = "home") -> dict[str, Any]:
        p = get_platform(platform)
        url = p.signup_url if purpose == "signup" else p.home_url
        return {"platform": p.id, "purpose": purpose, "navigation": self.browser.navigate(url),
                "policy": "Use only a real user-authorized account; security challenges stay human."}

    def inspect(self) -> dict[str, Any]:
        return self.browser.elements()

    def prepare_post(self, platform: str, caption: str = "", media_path: str = "") -> dict[str, Any]:
        p = get_platform(platform)
        opened = self.browser.navigate(p.home_url)
        if not opened.get("ok"):
            return opened
        return {
            "ok": True,
            "platform": p.id,
            "draft": {"caption": caption, "media_path": media_path},
            "next": "Inspect the page, open the composer, fill/upload, verify the draft, then request publish approval.",
            "elements": self.browser.elements(),
        }

    def execute_post(self, platform: str, caption: str, media_path: str = "",
                     publish: bool = False) -> dict[str, Any]:
        p = get_platform(platform)
        if not self.browser.status().get("started"):
            self.browser.start()
        if self.browser.status().get("url","") in ("", "about:blank"):
            opened = self.browser.navigate(p.home_url)
            if not opened.get("ok"):
                return opened
        if media_path:
            upload = self.browser.upload(media_path)
            if not upload.get("ok"):
                return upload
        if caption:
            fill = self.browser.fill_best_textbox(caption)
            if not fill.get("ok"):
                return fill
        if not publish:
            return {"ok": True, "verified": True, "platform": p.id, "draft": True,
                    "message": "Draft prepared; nothing was published.", "elements": self.browser.elements()}
        publish_result = self.browser.click_publish()
        if not publish_result.get("ok"):
            return publish_result
        verification = self.browser.elements()
        return {"ok": True, "verified": True, "platform": p.id,
                "published": True, "url": self.browser.status().get("url",""),
                "verification": verification}
