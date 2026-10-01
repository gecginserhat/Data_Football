"""Video hattı (Faz 5, ADR-0010): imzalı parçalı yükleme, gerçek ffmpeg ile HLS, oynatma listesi,
klip–duran top bağı, izinler ve kiracı izolasyonu.
"""

import subprocess
import time
import urllib.parse
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from kurgu_api.config import get_settings
from kurgu_api.video import storage
from kurgu_api.video.hls import ffmpeg_exe, parse_duration, rewrite_playlist
from kurgu_api.video.jobs import run_transcode
from kurgu_api.video.storage import LocalVideoStore, sign, verify

from .conftest import Seeded, TokenFactory
from .test_live import FakeQueue, _headers, _open, _sync, _upsert, club, match_id, queue

__all__ = ["club", "match_id", "queue"]

BASE = "http://test"


@pytest.fixture(autouse=True)
def local_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "objects"
    monkeypatch.setenv("KURGU_STORAGE_BACKEND", "local")
    monkeypatch.setenv("KURGU_STORAGE_DIR", str(root))
    monkeypatch.setenv("KURGU_PUBLIC_API_URL", BASE)
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """4 sn sentetik test görüntüsü ve ses (A-64); gerçek maç görüntüsü kullanılmaz."""
    path = tmp_path_factory.mktemp("video") / "sample.mp4"
    subprocess.run(  # noqa: S603
        [
            ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=4:size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
async def analyst(make_token: TokenFactory, superuser: asyncpg.Connection, club: Seeded) -> Any:
    return await _headers(make_token, superuser, club.tenant_a, "analyst")


def _path(url: str) -> str:
    assert url.startswith(BASE), url
    return url[len(BASE) :]


async def _upload(
    client: Any, headers: dict[str, str], data: bytes, match: str | None = None
) -> dict[str, Any]:
    created = await client.post(
        "/api/v1/video/uploads",
        headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
        json={
            "title": "SAM–TS geniş açı",
            "filename": "sample.mp4",
            "content_type": "video/mp4",
            "size_bytes": len(data),
            "match_id": match,
        },
    )
    assert created.status_code == 200, created.text
    body: dict[str, Any] = created.json()
    etags = []
    size = body["part_size"]
    for part in body["parts"]:
        chunk = data[(part["number"] - 1) * size : part["number"] * size]
        put = await client.put(_path(part["url"]), content=chunk)
        assert put.status_code == 200, put.text
        etags.append(put.headers["etag"])
    done = await client.post(
        f"/api/v1/video/assets/{body['asset']['id']}/complete",
        headers=headers,
        json={"etags": etags},
    )
    assert done.status_code == 200, done.text
    result: dict[str, Any] = done.json()
    return result


def test_signature_binds_method_key_and_expiry() -> None:
    secret = b"k"
    exp = int(time.time()) + 60
    signature = sign(secret, "PUT", "a/b", "u1", 1, exp)
    assert verify(secret, "PUT", "a/b", "u1", 1, exp, signature)
    assert not verify(secret, "GET", "a/b", "u1", 1, exp, signature)
    assert not verify(secret, "PUT", "a/c", "u1", 1, exp, signature)
    assert not verify(secret, "PUT", "a/b", "u1", 2, exp, signature)
    expired = int(time.time()) - 1
    assert not verify(
        secret, "PUT", "a/b", "u1", 1, expired, sign(secret, "PUT", "a/b", "u1", 1, expired)
    )


def test_playlist_rewrite_rejects_paths() -> None:
    playlist = "#EXTM3U\n#EXTINF:6.0,\nseg_00000.ts\n#EXT-X-ENDLIST\n"
    out = rewrite_playlist(playlist, lambda name: f"https://cdn/{name}?sig=1")
    assert "https://cdn/seg_00000.ts?sig=1" in out
    assert out.startswith("#EXTM3U\n#EXTINF:6.0,\n")
    with pytest.raises(RuntimeError):
        rewrite_playlist("#EXTM3U\n../secret.ts\n", lambda name: name)


def test_parse_duration() -> None:
    assert parse_duration("  Duration: 01:02:03.50, start: 0") == 3723.5
    assert parse_duration("nothing") is None


def test_local_store_rejects_traversal(local_storage: Path) -> None:
    store = LocalVideoStore(get_settings())
    with pytest.raises(ValueError, match="invalid object key"):
        store.path("../outside")
    with pytest.raises(ValueError, match="invalid upload id"):
        store.part_path("../x", 1)


async def test_upload_transcode_playlist_and_segments(
    client: Any,
    analyst: dict[str, str],
    match_id: str,
    queue: FakeQueue,
    sample_video: Path,
    club: Seeded,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage, "UPLOAD_TTL_S", 600)
    data = sample_video.read_bytes()  # noqa: ASYNC240
    # Küçük parçalarla çok parçalı yolu da sınar.
    monkeypatch.setattr("kurgu_api.video.router.PART_SIZE", 64 * 1024)
    asset = await _upload(client, analyst, data, match_id)

    assert asset["status"] == "processing"
    assert queue.jobs == [("transcode_video_job", asset["id"], str(club.tenant_a))]
    assert await run_transcode(asset["id"], str(club.tenant_a)) == "ready"

    ready = (await client.get(f"/api/v1/video/assets/{asset['id']}", headers=analyst)).json()
    assert ready["status"] == "ready"
    assert ready["duration_s"] == pytest.approx(4, abs=0.2)
    playlist = await client.get(f"/api/v1/video/assets/{asset['id']}/playlist", headers=analyst)
    assert playlist.status_code == 200
    assert playlist.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    segments = [line for line in playlist.text.splitlines() if line and not line.startswith("#")]
    assert segments
    segment = await client.get(_path(segments[0]))
    assert segment.status_code == 200
    assert segment.content[:1] == b"\x47"  # MPEG-TS senkron baytı

    parts = urllib.parse.urlsplit(segments[0])
    query = dict(urllib.parse.parse_qsl(parts.query))
    query["key"] = query["key"].replace("seg_", "seg_x")
    tampered = parts._replace(query=urllib.parse.urlencode(query)).geturl()
    assert (await client.get(_path(tampered))).status_code == 403

    deleted = await client.delete(f"/api/v1/video/assets/{asset['id']}", headers=analyst)
    assert deleted.status_code == 204
    assert (await client.get(_path(segments[0]))).status_code == 404


async def test_bad_etag_and_part_count_are_rejected(
    client: Any, analyst: dict[str, str], queue: FakeQueue
) -> None:
    created = await client.post(
        "/api/v1/video/uploads",
        headers=analyst | {"Idempotency-Key": "same"},
        json={"title": "x", "filename": "x.mp4", "content_type": "video/mp4", "size_bytes": 3},
    )
    again = await client.post(
        "/api/v1/video/uploads",
        headers=analyst | {"Idempotency-Key": "same"},
        json={"title": "x", "filename": "x.mp4", "content_type": "video/mp4", "size_bytes": 3},
    )
    assert created.json()["asset"]["id"] == again.json()["asset"]["id"]
    body = created.json()
    await client.put(_path(body["parts"][0]["url"]), content=b"abc")
    asset_id = body["asset"]["id"]

    wrong_count = await client.post(
        f"/api/v1/video/assets/{asset_id}/complete", headers=analyst, json={"etags": ["a", "b"]}
    )
    wrong_etag = await client.post(
        f"/api/v1/video/assets/{asset_id}/complete", headers=analyst, json={"etags": ['"00"']}
    )
    assert wrong_count.status_code == 422
    assert wrong_etag.status_code == 409
    assert queue.jobs == []


async def test_upload_rejects_unknown_type_and_huge_size(
    client: Any, analyst: dict[str, str]
) -> None:
    for payload in (
        {"content_type": "application/zip", "size_bytes": 10},
        {"content_type": "video/mp4", "size_bytes": 9 * 1024**3},
    ):
        response = await client.post(
            "/api/v1/video/uploads",
            headers=analyst | {"Idempotency-Key": str(uuid.uuid4())},
            json={"title": "x", "filename": "x", **payload},
        )
        assert response.status_code == 422


async def _ready_asset(
    superuser: asyncpg.Connection, tenant: uuid.UUID, match: str | None, duration: float = 6000
) -> str:
    asset_id = await superuser.fetchval(
        "insert into video_assets (tenant_id, match_id, title, filename, content_type, size_bytes,"
        " part_size, parts, storage_key, status, duration_s) values ($1, $2, 'v', 'v.mp4',"
        " 'video/mp4', 1, 1, 1, 'k', 'ready', $3) returning id",
        tenant,
        uuid.UUID(match) if match else None,
        duration,
    )
    return str(asset_id)


async def test_clip_links_set_piece_and_shows_in_routine_filter(
    client: Any,
    analyst: dict[str, str],
    match_id: str,
    superuser: asyncpg.Connection,
    club: Seeded,
) -> None:
    routine = await superuser.fetchval(
        "insert into routines (tenant_id, name, sp_type, current_version)"
        " values ($1, 'Kısa korner', 'corner', 1) returning id",
        club.tenant_a,
    )
    session_id = await _open(client, analyst, match_id)
    tag = uuid.uuid4()
    await _sync(client, analyst, session_id, [_upsert(tag, routine_id=str(routine))])
    asset = await _ready_asset(superuser, club.tenant_a, match_id)

    created = await client.post(
        "/api/v1/clips",
        headers=analyst,
        json={"asset_id": asset, "start_s": 750, "end_s": 770, "set_piece_id": str(tag)},
    )
    assert created.status_code == 201, created.text
    clip = created.json()
    assert clip["set_piece"]["id"] == str(tag)
    assert clip["set_piece"]["team_code"] == "TS"

    by_routine = await client.get("/api/v1/clips", headers=analyst, params={"routine_id": routine})
    assert [c["id"] for c in by_routine.json()] == [clip["id"]]

    moved = await client.patch(
        f"/api/v1/clips/{clip['id']}", headers=analyst, json={"end_s": 780, "title": "Arka direk"}
    )
    assert moved.status_code == 200
    assert (moved.json()["end_s"], moved.json()["set_piece"]["id"]) == (780, str(tag))

    unlinked = await client.patch(
        f"/api/v1/clips/{clip['id']}", headers=analyst, json={"set_piece_id": None}
    )
    assert unlinked.json()["set_piece"] is None
    deleted = await client.delete(f"/api/v1/clips/{clip['id']}", headers=analyst)
    assert deleted.status_code == 204


async def test_clip_validation(
    client: Any,
    analyst: dict[str, str],
    match_id: str,
    superuser: asyncpg.Connection,
    club: Seeded,
) -> None:
    session_id = await _open(client, analyst, match_id)
    tag = uuid.uuid4()
    await _sync(client, analyst, session_id, [_upsert(tag)])
    unmatched = await _ready_asset(superuser, club.tenant_a, None)
    short = await _ready_asset(superuser, club.tenant_a, match_id, duration=60)

    cases = [
        ({"asset_id": short, "start_s": 10, "end_s": 5}, 422),
        ({"asset_id": short, "start_s": 10, "end_s": 90}, 422),
        ({"asset_id": unmatched, "start_s": 1, "end_s": 5, "set_piece_id": str(tag)}, 422),
        ({"asset_id": short, "start_s": 1, "end_s": 5, "set_piece_id": str(uuid.uuid4())}, 404),
        ({"asset_id": str(uuid.uuid4()), "start_s": 1, "end_s": 5}, 404),
    ]
    for payload, status in cases:
        response = await client.post("/api/v1/clips", headers=analyst, json=payload)
        assert response.status_code == status, (payload, response.text)


async def test_viewer_reads_but_cannot_write(
    client: Any,
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    club: Seeded,
    match_id: str,
) -> None:
    viewer = await _headers(make_token, superuser, club.tenant_a, "viewer")
    asset = await _ready_asset(superuser, club.tenant_a, match_id)
    assert (await client.get("/api/v1/video/assets", headers=viewer)).status_code == 200
    assert (await client.get("/api/v1/clips", headers=viewer)).status_code == 200
    denied = await client.post(
        "/api/v1/clips", headers=viewer, json={"asset_id": asset, "start_s": 1, "end_s": 2}
    )
    assert denied.status_code == 403
    upload = await client.post(
        "/api/v1/video/uploads",
        headers=viewer | {"Idempotency-Key": "v"},
        json={"title": "x", "filename": "x", "content_type": "video/mp4", "size_bytes": 1},
    )
    assert upload.status_code == 403


async def test_videos_and_clips_are_tenant_isolated(
    client: Any,
    analyst: dict[str, str],
    make_token: TokenFactory,
    superuser: asyncpg.Connection,
    club: Seeded,
    match_id: str,
) -> None:
    other = await _headers(make_token, superuser, club.tenant_b, "analyst")
    asset = await _ready_asset(superuser, club.tenant_a, match_id)
    created = await client.post(
        "/api/v1/clips", headers=analyst, json={"asset_id": asset, "start_s": 1, "end_s": 2}
    )
    assert created.status_code == 201

    assert (await client.get(f"/api/v1/video/assets/{asset}", headers=other)).status_code == 404
    assert (await client.get("/api/v1/clips", headers=other)).json() == []
    foreign = await client.post(
        "/api/v1/clips", headers=other, json={"asset_id": asset, "start_s": 1, "end_s": 2}
    )
    assert foreign.status_code == 404
    gone = await client.delete(f"/api/v1/clips/{created.json()['id']}", headers=other)
    assert gone.status_code == 404
