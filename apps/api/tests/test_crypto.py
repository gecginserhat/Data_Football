"""Alan şifrelemesi (ADR-0014): zarf biçimi, AAD bağlama, anahtar döndürme ve ayar hataları."""

import base64
import json
import uuid

import asyncpg
import pytest
from kurgu_api.config import Settings
from kurgu_api.core.crypto import (
    DecryptError,
    KeyConfigError,
    Keyring,
    decrypt,
    encrypt,
    generate_key,
    rewrap,
)
from kurgu_api.ops.backup import with_database

from .conftest import ADMIN_URL, DB_NAME, Seeded

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


def test_rewrap_moves_envelope_to_primary_key_without_changing_value() -> None:
    old = Keyring.parse(f"k1:{_key(1)}")
    new = Keyring.parse(f"k2:{_key(2)},k1:{_key(1)}")
    tenant = uuid.uuid4()
    envelope = encrypt({"sleep": 3}, tenant_id=tenant, table="t", field="f", keyring=old)
    moved = rewrap(envelope, tenant_id=tenant, table="t", field="f", keyring=new)
    assert moved["kid"] == "k2"
    assert moved["ciphertext"] == envelope["ciphertext"]
    only_new = Keyring.parse(f"k2:{_key(2)}")
    assert decrypt(moved, tenant_id=tenant, table="t", field="f", keyring=only_new) == {"sleep": 3}
    assert rewrap(moved, tenant_id=tenant, table="t", field="f", keyring=new) is moved
    with pytest.raises(DecryptError):
        rewrap(envelope, tenant_id=uuid.uuid4(), table="t", field="f", keyring=new)


def test_generated_key_parses() -> None:
    entry = generate_key("2026-10")
    assert Keyring.parse(entry).primary == "2026-10"
    with pytest.raises(KeyConfigError):
        generate_key("bad,id")


async def test_rewrap_all_rotates_stored_wellness(
    monkeypatch: pytest.MonkeyPatch, superuser: asyncpg.Connection, tenants: Seeded
) -> None:
    from kurgu_api.ops import keys

    old = Keyring.parse(f"old:{_key(3)}")
    new = Keyring.parse(f"new:{_key(4)},old:{_key(3)}")
    player = await superuser.fetchval(
        "insert into squad_players (tenant_id, name, shirt_number, position, height_cm)"
        " values ($1, 'Döndürme', 41, 'FWD', 182) returning id",
        tenants.tenant_a,
    )
    envelope = encrypt(
        {"sleep": 2},
        tenant_id=tenants.tenant_a,
        table="wellness_entries",
        field="scores",
        keyring=old,
    )
    await superuser.execute(
        "insert into wellness_entries (tenant_id, squad_player_id, date, scores)"
        " values ($1, $2, '2026-09-01', $3::jsonb)",
        tenants.tenant_a,
        player,
        json.dumps(envelope),
    )
    monkeypatch.setattr(keys, "get_keyring", lambda: new)
    counts = await keys.rewrap_all(with_database(ADMIN_URL, DB_NAME), tenant=tenants.tenant_a)
    assert counts == {tenants.tenant_a: 1}
    stored = json.loads(
        await superuser.fetchval(
            "select scores::text from wellness_entries where squad_player_id = $1", player
        )
    )
    assert stored["kid"] == "new"
    assert decrypt(
        stored,
        tenant_id=tenants.tenant_a,
        table="wellness_entries",
        field="scores",
        keyring=Keyring.parse(f"new:{_key(4)}"),
    ) == {"sleep": 2}
    audit = await superuser.fetchval(
        "select after from audit_log where tenant_id = $1 and action = 'keys.rewrap'",
        tenants.tenant_a,
    )
    assert json.loads(audit)["kid"] == "new"
