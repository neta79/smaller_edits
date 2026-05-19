from __future__ import annotations

import base64
import hashlib
import math

from .models import ToolConfig


def canonicalize_line(content: str, *, trim_surrounding_spaces: bool = False) -> str:
    normalized = content.rstrip("\r\n")
    if trim_surrounding_spaces:
        return normalized.strip()
    return normalized


def _encode_digest(digest: bytes, width: int) -> str:
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    if len(encoded) >= width:
        return encoded[:width]

    extra = base64.urlsafe_b64encode(
        hashlib.blake2b(digest, digest_size=16).digest()
    ).decode("ascii").rstrip("=")
    return (encoded + extra)[:width]


def compute_chained_hashes(
    lines: list[str], config: ToolConfig | None = None
) -> list[str]:
    cfg = config or ToolConfig()
    digest_size = max(8, math.ceil(cfg.hash_width * 6 / 8))
    hashes: list[str] = []
    previous_hash = ""

    for index, line in enumerate(lines):
        canonical = canonicalize_line(
            line,
            trim_surrounding_spaces=cfg.trim_surrounding_spaces,
        )
        payload = canonical.encode("utf-8")
        if index > 0:
            payload = previous_hash.encode("ascii") + payload
        digest = hashlib.blake2b(payload, digest_size=digest_size).digest()
        encoded = _encode_digest(digest, cfg.hash_width)
        hashes.append(encoded)
        previous_hash = encoded

    return hashes
