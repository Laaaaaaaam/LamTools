import base64
import hashlib
import os
import logging
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


def _get_seed_file_path() -> Path:
    from app.config import settings
    return settings.DATA_DIR / ".encryption_seed"


def _get_or_create_seed() -> bytes:
    """Get or create a stable encryption seed file.
    Uses a file-based seed (not machine fingerprint) so keys survive
    machine changes, OS reinstalls, and PyInstaller re-bundling.
    """
    seed_file = _get_seed_file_path()
    if seed_file.exists():
        return seed_file.read_bytes()
    seed = os.urandom(32)
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    seed_file.write_bytes(seed)
    logger.info("Created new encryption seed at %s", seed_file)
    return seed


def _derive_key() -> bytes:
    seed = _get_or_create_seed()
    return hashlib.sha256(b"lamartist:v2:" + seed).digest()


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode("ascii")


def decrypt(ciphertext_b64: str) -> str:
    if not ciphertext_b64:
        return ""
    key = _derive_key()
    combined = base64.b64decode(ciphertext_b64)
    nonce = combined[:12]
    ciphertext = combined[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def mask_key(key: str) -> str:
    if not key or len(key) <= 4:
        return "****"
    return "****" + key[-4:]
