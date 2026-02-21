from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import subprocess
import os


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
    env_key = f"{name.upper()}_BIN"
    env_bin = os.getenv(env_key)
    if env_bin:
        resolved_env = shutil.which(env_bin) or (env_bin if Path(env_bin).exists() else None)
        if resolved_env:
            return resolved_env
    resolved = shutil.which(name)
    if not resolved:
        fallback = _find_winget_ffmpeg_binary(name)
        if fallback:
            return fallback
        raise ValidationError(
            f"Required executable not found in PATH: {name} "
            f"(or set {env_key} to an explicit executable path)"
        )
    return resolved


def _find_winget_ffmpeg_binary(name: str) -> str | None:
    local_app_data = os.getenv("LOCALAPPDATA")
    if not local_app_data:
        return None
    root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not root.exists():
        return None
    pattern = f"Gyan.FFmpeg_*/*/bin/{name}.exe"
    matches = sorted(root.glob(pattern), reverse=True)
    for match in matches:
        if match.exists():
            return str(match)
    return None


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


def media_has_audio_stream(ffprobe_bin: str, path: Path) -> bool:
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = run_command(cmd, capture_output=True)
    if result is None:
        return False
    return bool(result.stdout.strip())


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
