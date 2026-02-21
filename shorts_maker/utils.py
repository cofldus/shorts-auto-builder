from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import subprocess


class ShortsMakerError(Exception):
    """Base error for shorts maker."""


class ValidationError(ShortsMakerError):
    """Input validation error."""


class FFmpegError(ShortsMakerError):
    """ffmpeg execution error."""


_VERBOSE = False


def set_verbose(enabled: bool) -> None:
    global _VERBOSE
    _VERBOSE = enabled


def _format_command(args: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in args)


def ensure_executable(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise ValidationError(f"Required executable not found in PATH: {name}")
    return resolved


def run_command(args: list[str], capture_output: bool = False) -> subprocess.CompletedProcess[str] | None:
    if _VERBOSE:
        print(f"[cmd] {_format_command(args)}")
    try:
        return subprocess.run(
            args,
            check=True,
            text=True,
            capture_output=capture_output,
        )
    except subprocess.CalledProcessError as exc:
        joined = _format_command(args)
        stderr = f"\n{exc.stderr}" if exc.stderr else ""
        raise FFmpegError(f"Command failed ({exc.returncode}): {joined}{stderr}") from exc


def probe_media_duration(ffprobe_bin: str, path: Path) -> float:
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = run_command(cmd, capture_output=True)
    if result is None or not result.stdout.strip():
        raise ValidationError(f"Unable to probe media duration: {path}")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise ValidationError(f"Invalid duration from ffprobe for file: {path}") from exc


def ffmpeg_has_filter(ffmpeg_bin: str, filter_name: str) -> bool:
    result = run_command([ffmpeg_bin, "-hide_banner", "-filters"], capture_output=True)
    if result is None:
        return False
    lines = result.stdout.splitlines()
    token = f" {filter_name} "
    return any(token in line for line in lines)


def preflight_check(*, subtitles_enabled: bool) -> tuple[str, str]:
    ffmpeg_bin = ensure_executable("ffmpeg")
    ffprobe_bin = ensure_executable("ffprobe")
    if subtitles_enabled and not ffmpeg_has_filter(ffmpeg_bin, "subtitles"):
        raise ValidationError(
            "FFmpeg subtitles filter is unavailable. Install FFmpeg with libass support "
            "(the 'subtitles' filter)."
        )
    return ffmpeg_bin, ffprobe_bin


def ensure_path_exists(path: Path, path_type: str = "path") -> None:
    if not path.exists():
        raise ValidationError(f"{path_type.capitalize()} does not exist: {path}")
