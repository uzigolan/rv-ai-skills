from __future__ import annotations

import os
from pathlib import Path


def protect(plaintext: str, key_path: Path) -> str:
    return _fernet_protect(plaintext, key_path)


def unprotect(ciphertext: str, key_path: Path) -> str:
    return _fernet_unprotect(ciphertext, key_path)


def _fernet_key_path(key_path: Path) -> Path:
    key_path.parent.mkdir(parents=True, exist_ok=True)
    return key_path


def _load_or_create_key(key_path: Path) -> bytes:
    key_path = _fernet_key_path(key_path)
    if key_path.exists():
        return key_path.read_bytes()
    key = _generate_fernet_key()
    key_path.write_bytes(key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key


def _generate_fernet_key() -> bytes:
    try:
        from cryptography.fernet import Fernet
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("cryptography is required for Linux/macOS encryption") from exc
    return Fernet.generate_key()


def _fernet_protect(plaintext: str, key_path: Path) -> str:
    from cryptography.fernet import Fernet

    key = _load_or_create_key(key_path)
    f = Fernet(key)
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def _fernet_unprotect(ciphertext: str, key_path: Path) -> str:
    from cryptography.fernet import Fernet

    key = _load_or_create_key(key_path)
    f = Fernet(key)
    try:
        data = f.decrypt(ciphertext.encode("ascii"))
        return data.decode("utf-8")
    except Exception:
        return ""
