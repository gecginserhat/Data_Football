"""ffmpeg ile HLS dönüştürme (A-61). ffmpeg ikilisi `imageio-ffmpeg` paketinden gelir."""

import asyncio
import re
import shutil
from collections.abc import Callable
from pathlib import Path

PLAYLIST = "index.m3u8"
SEGMENT_PATTERN = "seg_%05d.ts"
DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


class TranscodeError(RuntimeError):
    pass


def ffmpeg_exe() -> str:
    """Sistemdeki ffmpeg varsa o, yoksa paketle gelen derlenmiş ikili."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg

    exe: str = imageio_ffmpeg.get_ffmpeg_exe()
    return exe


def parse_duration(stderr: str) -> float | None:
    """ffmpeg günlüğündeki `Duration: SS:DD:SS.ss` satırından saniye."""
    match = DURATION_RE.search(stderr)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def hls_command(exe: str, source: Path, out_dir: Path) -> list[str]:
    """Tek kalite: en çok 720 satır, H.264 + AAC, 6 sn parça, VOD oynatma listesi."""
    return [
        exe,
        "-hide_banner",
        "-nostdin",
        "-y",
        # Girdi yalnız yerel dosya ve yalnız kabul edilen kapsayıcılar (A-98): oynatma listesi ya da
        # ağ adresi içeren bir dosya ffmpeg'e başka kaynak okutamaz.
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        "mov,matroska",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        "scale=-2:'min(720,ih)'",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ac",
        "2",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        str(out_dir / SEGMENT_PATTERN),
        str(out_dir / PLAYLIST),
    ]


async def transcode(source: Path, out_dir: Path) -> float | None:
    """Kaynağı HLS'ye çevirir; videonun süresini (sn) döner."""
    await asyncio.to_thread(out_dir.mkdir, parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        *hls_command(ffmpeg_exe(), source, out_dir),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    log = stderr.decode(errors="replace")
    produced = await asyncio.to_thread((out_dir / PLAYLIST).exists)
    if process.returncode != 0 or not produced:
        raise TranscodeError(log[-2000:])
    return parse_duration(log)


def rewrite_playlist(playlist: str, url_for: Callable[[str], str]) -> str:
    """Parça satırlarını imzalı adreslerle değiştirir; etiket satırları aynen kalır."""
    lines = []
    for line in playlist.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if "/" in stripped or ".." in stripped:
                raise TranscodeError("unexpected segment path in playlist")
            lines.append(url_for(stripped))
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"
