"""Alan düzeyinde zarf şifrelemesi (ADR-0014).

Her değer için rastgele 256 bit veri anahtarı (DEK) üretilir; değer AES-256-GCM ile bu anahtarla,
DEK de anahtar şifreleme anahtarıyla (KEK) şifrelenir. Saklanan biçim sürümlü JSON zarfıdır:
`{v, kid, wrapped_dek, nonce, ciphertext}`. İlişkili veri (AAD) kiracı, tablo ve alan adını bağlar;
başka kiracıya ya da alana kopyalanan zarf çözülmez.

KEK'ler `KURGU_DATA_KEYS` değişkeninden okunur: virgülle ayrılmış `kid:base64` listesi, ilk anahtar
yeni kayıtları şifreler, diğerleri yalnız okumada kullanılır. Geliştirme ve testte değişken boşsa
sabit geliştirme anahtarı kullanılır; diğer ortamlarda anahtar yoksa uygulama başlamaz.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from kurgu_api.config import Settings, get_settings

VERSION = 1
NONCE_BYTES = 12
DEV_KID = "dev"
# Gizli değildir: yalnız geliştirme ve test verisini korur, üretimde kullanılmaz.
_DEV_KEY = hashlib.sha256(b"kurgu-development-data-key").digest()


class KeyConfigError(RuntimeError):
    """Anahtar ayarı eksik ya da geçersiz."""


class DecryptError(ValueError):
    """Zarf çözülemedi (yanlış anahtar, kiracı, alan ya da bozulmuş veri)."""


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"), validate=True)


@dataclass(frozen=True)
class Keyring:
    keys: dict[str, bytes]
    primary: str

    @classmethod
    def parse(cls, value: str) -> Keyring:
        keys: dict[str, bytes] = {}
        order: list[str] = []
        for item in (p.strip() for p in value.split(",")):
            if not item:
                continue
            kid, sep, encoded = item.partition(":")
            if not sep or not kid:
                raise KeyConfigError("KURGU_DATA_KEYS entries must look like kid:base64")
            try:
                key = _b64d(encoded)
            except ValueError as exc:
                raise KeyConfigError(f"key {kid!r} is not valid base64") from exc
            if len(key) != 32:
                raise KeyConfigError(f"key {kid!r} must be 32 bytes")
            if kid in keys:
                raise KeyConfigError(f"duplicate key id {kid!r}")
            keys[kid] = key
            order.append(kid)
        if not order:
            raise KeyConfigError("KURGU_DATA_KEYS is empty")
        return cls(keys, order[0])

    @classmethod
    def from_settings(cls, settings: Settings) -> Keyring:
        if settings.kurgu_data_keys:
            return cls.parse(settings.kurgu_data_keys)
        if settings.kurgu_env in {"development", "test"}:
            return cls({DEV_KID: _DEV_KEY}, DEV_KID)
        raise KeyConfigError(f"KURGU_DATA_KEYS is required in {settings.kurgu_env}")


@lru_cache
def get_keyring() -> Keyring:
    return Keyring.from_settings(get_settings())


def _aad(tenant_id: uuid.UUID, table: str, field: str) -> bytes:
    return f"kurgu:v{VERSION}:{tenant_id}:{table}:{field}".encode()


def encrypt(
    value: Any, *, tenant_id: uuid.UUID, table: str, field: str, keyring: Keyring | None = None
) -> dict[str, Any]:
    """JSON'a dönüştürülebilir değeri şifreler ve saklanacak zarfı döner."""
    ring = keyring or get_keyring()
    aad = _aad(tenant_id, table, field)
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(dek).encrypt(nonce, json.dumps(value).encode(), aad)
    wrap_nonce = os.urandom(NONCE_BYTES)
    wrapped = AESGCM(ring.keys[ring.primary]).encrypt(wrap_nonce, dek, aad)
    return {
        "v": VERSION,
        "kid": ring.primary,
        "wrapped_dek": _b64e(wrap_nonce + wrapped),
        "nonce": _b64e(nonce),
        "ciphertext": _b64e(ciphertext),
    }


def decrypt(
    envelope: dict[str, Any],
    *,
    tenant_id: uuid.UUID,
    table: str,
    field: str,
    keyring: Keyring | None = None,
) -> Any:
    """Zarfı çözer. Anahtar, kiracı ya da alan uyuşmazsa `DecryptError`."""
    ring = keyring or get_keyring()
    if envelope.get("v") != VERSION:
        raise DecryptError("unsupported envelope version")
    key = ring.keys.get(str(envelope.get("kid")))
    if key is None:
        raise DecryptError("unknown key id")
    aad = _aad(tenant_id, table, field)
    try:
        wrapped = _b64d(envelope["wrapped_dek"])
        dek = AESGCM(key).decrypt(wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:], aad)
        plain = AESGCM(dek).decrypt(_b64d(envelope["nonce"]), _b64d(envelope["ciphertext"]), aad)
    except Exception as exc:  # InvalidTag, KeyError, base64 hataları
        raise DecryptError("envelope could not be decrypted") from exc
    return json.loads(plain)


def rewrap(
    envelope: dict[str, Any],
    *,
    tenant_id: uuid.UUID,
    table: str,
    field: str,
    keyring: Keyring | None = None,
) -> dict[str, Any]:
    """Anahtar döndürme: DEK'i birincil KEK ile yeniden sarar; şifreli değer değişmez.

    Zarf zaten birincil anahtarla sarılıysa aynen döner. Eski anahtar bilinmiyorsa `DecryptError`.
    """
    ring = keyring or get_keyring()
    if envelope.get("kid") == ring.primary:
        return envelope
    # Önce tüm zarfın çözüldüğü doğrulanır; bozuk bir zarf yeni anahtarla mühürlenmez.
    decrypt(envelope, tenant_id=tenant_id, table=table, field=field, keyring=ring)
    aad = _aad(tenant_id, table, field)
    old = ring.keys[str(envelope["kid"])]
    wrapped = _b64d(envelope["wrapped_dek"])
    dek = AESGCM(old).decrypt(wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:], aad)
    wrap_nonce = os.urandom(NONCE_BYTES)
    rewrapped = AESGCM(ring.keys[ring.primary]).encrypt(wrap_nonce, dek, aad)
    return {**envelope, "kid": ring.primary, "wrapped_dek": _b64e(wrap_nonce + rewrapped)}


def generate_key(kid: str) -> str:
    """`KURGU_DATA_KEYS` için yeni bir `kid:base64` girdisi."""
    if not kid or "," in kid or ":" in kid:
        raise KeyConfigError("key id must be non-empty and contain no ',' or ':'")
    return f"{kid}:{_b64e(os.urandom(32))}"
