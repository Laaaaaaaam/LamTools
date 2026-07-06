from __future__ import annotations
import base64
import re

import aiohttp

from app.utils.llm_client import get_shared_session


class ImageGenError(Exception):
    pass


class ImageGenConnectionError(ImageGenError):
    pass


class ImageGenResponseError(ImageGenError):
    pass


class ImageGenNotSupportedError(ImageGenError):
    pass


class ImageClient:
    def __init__(self, base_url: str, api_key: str, model_id: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        n: int = 1,
        size: str = "1024x1024",
        reference_images: list[str] | None = None,
        **kwargs,
    ) -> dict:
        url = f"{self.base_url}/v1/images/generations"
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "n": n,
            "size": size,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if reference_images:
            payload["reference_images"] = reference_images
        payload.update(kwargs)

        try:
            session = await get_shared_session()
            async with session.post(
                url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ImageGenResponseError(f"Image API error {resp.status}: {text}")
                data = await resp.json()
                return data
        except aiohttp.ClientError as e:
            raise ImageGenConnectionError(f"Connection error: {e}") from e

    async def chat_edit(
        self,
        prompt: str,
        images: list[str],
        n: int = 1,
        size: str = "1024x1024",
        reference_labels: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        url = f"{self.base_url}/v1/chat/completions"

        labels = reference_labels or []
        image_label_lines = []
        for i in range(len(images)):
            name = labels[i]["name"] if i < len(labels) else f"图片{i+1}"
            image_label_lines.append(f"  [图{i+1}]: {name}")
        label_hint = ""
        if image_label_lines:
            label_hint = "你收到了以下参考图片，编号与图片顺序一一对应：\n" + "\n".join(image_label_lines) + "\n\n"

        content_parts: list[dict] = []
        content_parts.append({
            "type": "text",
            "text": (
                f"{label_hint}"
                f"请根据参考图片和以下指令生成新图片。"
                f"直接返回生成的图片，不要描述或解释。\n\n指令: {prompt}"
            ),
        })
        for img in images:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": img, "detail": "auto"},
            })

        payload = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": 4096,
        }
        payload.update(kwargs)

        import logging as _log
        _l = _log.getLogger(__name__)
        _l.debug(f"chat_edit request: base_url={self.base_url}, model={self.model_id}")
        _l.debug(f"chat_edit images count: {len(images)}")
        for i, img in enumerate(images):
            _l.debug(f"chat_edit image[{i}]: prefix={img[:60]}... length={len(img)}")
        payload_log = dict(payload)
        _l.debug(f"chat_edit payload keys: {list(payload_log.keys())}")

        try:
            session = await get_shared_session()
            async with session.post(
                url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ImageGenNotSupportedError(f"Chat API error {resp.status}: {text[:500]}")
                data = await resp.json()
                import logging
                logging.getLogger(__name__).debug(f"chat_edit response keys: {list(data.keys())}")
                return data
        except aiohttp.ClientError as e:
            raise ImageGenConnectionError(f"Connection error: {e}") from e

    async def edit(
        self,
        prompt: str,
        images: list[str],
        n: int = 1,
        size: str = "1024x1024",
        input_fidelity: str | None = None,
        **kwargs,
    ) -> dict:
        url = f"{self.base_url}/v1/images/edits"
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "images": [{"image_url": img} for img in images],
            "n": n,
            "size": size,
        }
        if input_fidelity:
            payload["input_fidelity"] = input_fidelity
        payload.update(kwargs)

        try:
            session = await get_shared_session()
            async with session.post(
                url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ImageGenResponseError(f"Image API error {resp.status}: {text}")
                data = await resp.json()
                return data
        except aiohttp.ClientError as e:
            raise ImageGenConnectionError(f"Connection error: {e}") from e

    async def test_connection(self) -> bool:
        try:
            result = await self.generate(
                prompt="test",
                n=1,
                size="256x256",
            )
            return "data" in result or "images" in result
        except ImageGenError:
            return False

    @staticmethod
    def extract_images(response: dict) -> list[str]:
        images = []
        for item in response.get("data", []):
            if "url" in item:
                images.append(item["url"])
            elif "b64_json" in item:
                images.append(f"data:image/png;base64,{item['b64_json']}")
        return images

    @staticmethod
    def extract_images_from_chat(response: dict) -> list[str]:
        images: list[str] = []
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            for img in message.get("images", []):
                if isinstance(img, dict):
                    if img.get("type") == "image_url":
                        url = img.get("image_url", {}).get("url", "")
                    elif img.get("type") == "image":
                        url = img.get("image", "")
                    else:
                        url = str(img)
                else:
                    url = str(img)
                if url:
                    images.append(url)
            content = message.get("content", "")
            if content and isinstance(content, str):
                markdown_images = re.findall(r'!\[.*?\]\((https?://[^\s)]+)\)', content)
                for url in markdown_images:
                    if url not in images:
                        images.append(url)
                data_urls = re.findall(r'!\[.*?\]\((data:image/[^)]+)\)', content)
                for url in data_urls:
                    if url not in images:
                        images.append(url)
        if not images:
            data = response.get("data", [])
            if data:
                for item in data:
                    url = item.get("url") or item.get("image_url", {}).get("url", "")
                    if url:
                        images.append(url)
        return images

    @staticmethod
    async def urls_to_base64(urls: list[str]) -> list[str]:
        result = []
        session = await get_shared_session()
        for url in urls[:6]:
            if url.startswith("data:"):
                result.append(url)
                continue
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        mimetype = resp.content_type or "image/png"
                        b64 = base64.b64encode(data).decode("utf-8")
                        result.append(f"data:{mimetype};base64,{b64}")
            except Exception:
                continue
        return result
