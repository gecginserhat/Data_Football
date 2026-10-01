"""Alan şifrelemesi (ADR-0014): zarf biçimi, AAD bağlama, anahtar döndürme ve ayar hataları."""

import base64
import uuid

import pytest
from kurgu_api.config import Settings
from kurgu_api.core.crypto import DecryptError, KeyConfigError, Keyring, decrypt, encrypt

T1 = uuid.UUID("00000000-0000-4000-9000-0000000000a1")
T2 = uuid.UUID("00000000-0000-4000-9000-0000000000a2")
VALUE = {"sleep": 3, "stress": 2, "fatigue": 5, "soreness": 4}


def _key(byte: int) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode()


def _ring(spec: str) -> Keyring:
    return Keyring.parse(spec)


def test_round_trip_and_envelope_shape() -> None:
    ring = _ring(f"k1:{_key(1)}")
    env = encrypt(VALUE, tenant_id=T1, table="wellness_entries", field="scores", keyring=ring)
    assert set(env) == {"v", "kid", "wrapped_dek", "nonce", "ciphertext"}
    assert env["kid"] == "k1"
    assert "sleep" not in env["ciphertext"]
    out = decrypt(env, tenant_id=T1, table="wellness_entries", field="scores", keyring=ring)
    assert out == VALUE
    # Her değer kendi rastgele anahtarıyla şifrelenir.
    again = encrypt(VALUE, tenant_id=T1, table="wellness_entries", field="scores", keyring=ring)
    assert again["ciphertext"] != env["ciphertext"]
    assert again["wrapped_dek"] != env["wrapped_dek"]


@pytest.mark.parametrize(
    ("tenant", "table", "field"),
    [(T2, "wellness_entries", "scores"), (T1, "other", "scores"), (T1, "wellness_entries", "x")],
)
def test_envelope_is_bound_to_tenant_table_and_field(
    tenant: uuid.UUID, table: str, field: str
) -> None:
    ring = _ring(f"k1:{_key(1)}")
    env = encrypt(VALUE, tenant_id=T1, table="wellness_entries", field="scores", keyring=ring)
    with pytest.raises(DecryptError):
        decrypt(env, tenant_id=tenant, table=table, field=field, keyring=ring)


def test_tampering_and_wrong_key_fail() -> None:
    ring = _ring(f"k1:{_key(1)}")
    env = encrypt(VALUE, tenant_id=T1, table="t", field="f", keyring=ring)
    raw = bytearray(base64.b64decode(env["ciphertext"]))
    raw[0] ^= 1
    with pytest.raises(DecryptError):
        decrypt(
            {**env, "ciphertext": base64.b64encode(raw).decode()},
            tenant_id=T1,
            table="t",
            field="f",
            keyring=ring,
        )
    with pytest.raises(DecryptError):
        decrypt(env, tenant_id=T1, table="t", field="f", keyring=_ring(f"k1:{_key(2)}"))
    with pytest.raises(DecryptError):
        decrypt(env, tenant_id=T1, table="t", field="f", keyring=_ring(f"k9:{_key(1)}"))
    with pytest.raises(DecryptError):
        decrypt({**env, "v": 2}, tenant_id=T1, table="t", field="f", keyring=ring)


def test_rotation_reads_old_key_and_writes_new() -> None:
    old = _ring(f"k1:{_key(1)}")
    env = encrypt(VALUE, tenant_id=T1, table="t", field="f", keyring=old)
    rotated = _ring(f"k2:{_key(2)},k1:{_key(1)}")
    assert decrypt(env, tenant_id=T1, table="t", field="f", keyring=rotated) == VALUE
    assert encrypt(VALUE, tenant_id=T1, table="t", field="f", keyring=rotated)["kid"] == "k2"


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "nokey",
        f":{_key(1)}",
        "k1:not-base64!",
        f"k1:{base64.b64encode(b'x' * 16).decode()}",
        f"k1:{_key(1)},k1:{_key(2)}",
    ],
)
def test_invalid_key_config(spec: str) -> None:
    with pytest.raises(KeyConfigError):
        Keyring.parse(spec)


def test_dev_key_only_outside_production() -> None:
    assert Keyring.from_settings(Settings(kurgu_env="test", kurgu_data_keys=None)).primary == "dev"
    with pytest.raises(KeyConfigError):
        Keyring.from_settings(Settings(kurgu_env="production", kurgu_data_keys=None))
    ring = Keyring.from_settings(Settings(kurgu_env="production", kurgu_data_keys=f"p1:{_key(7)}"))
    assert ring.primary == "p1"
