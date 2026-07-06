import threading
from typing import Callable

import pystray
from PIL import Image, ImageDraw, ImageFont


def _create_default_icon() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.ellipse([4, 4, size - 4, size - 4], fill="#333333")

    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except (OSError, IOError):
        font = ImageFont.load_default()

    text = "L"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) / 2
    y = (size - th) / 2 - 2
    draw.text((x, y), text, fill="white", font=font)

    return img


class TrayManager:
    def __init__(
        self,
        on_show: Callable[[], None],
        on_assistant: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        self._on_show = on_show
        self._on_assistant = on_assistant
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        icon_image = _create_default_icon()
        menu = pystray.Menu(
            pystray.MenuItem("主程序", self._on_show, default=True),
            pystray.MenuItem("助手", self._on_assistant),
            pystray.MenuItem("设置", self._on_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._on_quit),
        )
        self._icon = pystray.Icon("lamartist", icon_image, "lamartist", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def update_icon(self, icon_path: str) -> None:
        if self._icon:
            try:
                img = Image.open(icon_path)
                self._icon.icon = img
            except Exception:
                pass

    def notify(self, title: str, message: str) -> None:
        if self._icon:
            self._icon.notify(message, title)
