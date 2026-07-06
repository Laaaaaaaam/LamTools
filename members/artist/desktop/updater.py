from __future__ import annotations

import json
import platform
import urllib.request
from dataclasses import dataclass


@dataclass
class UpdateInfo:
    version: str
    download_url: str
    release_notes: str


class UpdateChecker:
    def __init__(self, repo: str, current_version: str):
        self._repo = repo
        self._current_version = current_version

    def check(self) -> UpdateInfo | None:
        try:
            url = f"https://api.github.com/repos/{self._repo}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "lamartist"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            latest = data.get("tag_name", "").lstrip("v")
            if not latest:
                return None

            if not self._is_newer(latest, self._current_version):
                return None

            download_url = self._get_download_url(data)
            release_notes = data.get("body", "") or ""

            return UpdateInfo(
                version=latest,
                download_url=download_url,
                release_notes=release_notes,
            )
        except Exception:
            return None

    def _is_newer(self, latest: str, current: str) -> bool:
        try:
            latest_parts = [int(x) for x in latest.split(".")]
            current_parts = [int(x) for x in current.split(".")]
            return latest_parts > current_parts
        except (ValueError, TypeError):
            return latest != current

    def _get_download_url(self, release: dict) -> str:
        system = platform.system().lower()
        assets = release.get("assets", [])

        platform_keywords = {
            "windows": [".exe", "windows", "win"],
            "darwin": ["macos", "darwin", ".dmg", ".app"],
            "linux": ["linux", ".appimage", ".deb"],
        }

        keywords = platform_keywords.get(system, [])
        for asset in assets:
            name = asset.get("name", "").lower()
            if any(kw in name for kw in keywords):
                return asset.get("browser_download_url", "")

        html_url = release.get("html_url", "")
        return html_url
