from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .script_parser import Segment
from .utils import ValidationError, probe_media_duration, run_command


@dataclass(frozen=True)
class NarrationResult:
    track_path: Path
    warnings: list[str]


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _has_narration(seg: Segment) -> bool:
    return bool(seg.narration and seg.narration.strip())


def _generate_tts_edge(segment_text: str, voice: str, out_wav_path: Path) -> None:
    try:
        import asyncio
        import edge_tts
    except ImportError as exc:
        raise ValidationError(
            "edge-tts is required for --voice edge. Install dependencies from requirements.txt."
        ) from exc

    async def _save() -> None:
        communicate = edge_tts.Communicate(text=segment_text, voice=voice)
        await communicate.save(str(out_wav_path))

    try:
        asyncio.run(_save())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_save())
        finally:
            loop.close()


def _generate_tts_openai(segment_text: str, voice: str, lang: str, out_wav_path: Path) -> None:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValidationError("openai 패키지가 필요합니다. requirements.txt를 다시 설치하세요.") from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValidationError("OPENAI_API_KEY 환경 변수가 필요합니다.")

    voice_name = voice if "-" not in voice else "alloy"
    model_name = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    guidance = f"Speak naturally in {lang}. Keep a warm and clear tone."

    client = OpenAI(api_key=api_key)
    try:
        with client.audio.speech.with_streaming_response.create(
            model=model_name,
            voice=voice_name,
            input=segment_text,
            response_format="wav",
            instructions=guidance,
        ) as response:
            response.stream_to_file(str(out_wav_path))
    except Exception as exc:
        raise ValidationError(f"OpenAI TTS 생성 실패: {exc}") from exc


def generate_tts(
    segment_text: str,
    mode: str,
    voice: str,
    lang: str,
    out_wav_path: Path,
) -> None:
    if not segment_text.strip():
        raise ValidationError("Cannot generate TTS for empty narration text")

    out_wav_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "edge":
        _generate_tts_edge(segment_text=segment_text, voice=voice, out_wav_path=out_wav_path)
        return
    if mode == "openai":
        _generate_tts_openai(
            segment_text=segment_text,
            voice=voice,
            lang=lang,
            out_wav_path=out_wav_path,
        )
        return

    raise ValidationError(f"Unsupported voice mode for TTS generation: {mode}")


def _time_stretch_and_fit(
    ffmpeg_bin: str,
    ffprobe_bin: str,
    input_wav: Path,
    output_wav: Path,
    target_duration: float,
) -> str | None:
    current = probe_media_duration(ffprobe_bin, input_wav)
    warning: str | None = None

    stretch = 1.0
    if current > target_duration:
        stretch = min(1.1, current / target_duration)
    atempo = f"atempo={stretch:.6f}" if stretch > 1.0 else "anull"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_wav),
        "-filter:a",
        f"{atempo},apad=pad_dur={target_duration:.3f},atrim=0:{target_duration:.3f}",
        "-ar",
        "48000",
        "-ac",
        "2",
        str(output_wav),
    ]
    run_command(cmd)

    adjusted = probe_media_duration(ffprobe_bin, output_wav)
    if current > target_duration and stretch >= 1.1 and adjusted >= target_duration - 0.02:
        warning = (
            f"Narration clip exceeded segment duration (orig {current:.2f}s > {target_duration:.2f}s). "
            "Applied max 1.1x speed-up and trimmed remainder."
        )
    return warning


def _build_narration_track(
    ffmpeg_bin: str,
    ffprobe_bin: str,
    segments: list[Segment],
    duration: float,
    voice_mode: str,
    voice: str,
    voice_lang: str,
    work_dir: Path,
) -> NarrationResult:
    warnings: list[str] = []
    fitted_paths: list[tuple[Path, int]] = []

    for idx, seg in enumerate(segments):
        if not _has_narration(seg):
            continue
        raw_wav = work_dir / f"tts_raw_{idx:04d}.wav"
        fitted_wav = work_dir / f"tts_fit_{idx:04d}.wav"

        generate_tts(
            seg.narration or "",
            mode=voice_mode,
            voice=voice,
            lang=voice_lang,
            out_wav_path=raw_wav,
        )
        warning = _time_stretch_and_fit(
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
            input_wav=raw_wav,
            output_wav=fitted_wav,
            target_duration=seg.duration,
        )
        if warning:
            warnings.append(f"Segment {idx + 1}: {warning}")

        delay_ms = int(seg.start * 1000)
        fitted_paths.append((fitted_wav, delay_ms))

    narration_track = work_dir / "narration_full.wav"
    if not fitted_paths:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            str(narration_track),
        ]
        run_command(cmd)
        return NarrationResult(track_path=narration_track, warnings=warnings)

    cmd = [ffmpeg_bin, "-y"]
    for path, _ in fitted_paths:
        cmd.extend(["-i", str(path)])

    filter_parts: list[str] = []
    mix_labels: list[str] = []
    for i, (_, delay_ms) in enumerate(fitted_paths):
        label = f"a{i}"
        filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},volume=1.0[{label}]")
        mix_labels.append(f"[{label}]")

    filter_parts.append(
        f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:normalize=0,atrim=0:{duration:.3f}[mixout]"
    )

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[mixout]",
            "-c:a",
            "pcm_s16le",
            str(narration_track),
        ]
    )
    run_command(cmd)
    return NarrationResult(track_path=narration_track, warnings=warnings)


def _build_duck_volume_expression(
    narration_ranges: list[tuple[float, float]],
    duck_gain: float,
    fade: float,
) -> str:
    expr = "1"
    for start, end in narration_ranges:
        if end <= start:
            continue
        if fade <= 0:
            expr = f"if(between(t,{start:.3f},{end:.3f}),{duck_gain:.6f},{expr})"
            continue
        in_start = max(0.0, start - fade)
        out_end = end + fade
        down = (
            f"(1-(1-{duck_gain:.6f})*((t-{in_start:.3f})/{max(0.001, (start-in_start)):.3f}))"
            if start > in_start
            else f"{duck_gain:.6f}"
        )
        up = (
            f"({duck_gain:.6f}+(1-{duck_gain:.6f})*((t-{end:.3f})/{max(0.001, (out_end-end)):.3f}))"
            if out_end > end
            else "1"
        )
        expr = (
            f"if(between(t,{in_start:.3f},{start:.3f}),{down},"
            f"if(between(t,{start:.3f},{end:.3f}),{duck_gain:.6f},"
            f"if(between(t,{end:.3f},{out_end:.3f}),{up},{expr})))"
        )
    return expr


def build_final_audio_track(
    ffmpeg_bin: str,
    ffprobe_bin: str,
    segments: list[Segment],
    duration: float,
    voice_mode: str,
    voice_lang: str,
    voice_voice: str,
    bgm_path: str | None,
    fade: float,
    work_dir: Path,
) -> NarrationResult:
    if duration <= 0:
        raise ValidationError("Duration must be > 0 for audio track generation")

    narration = _build_narration_track(
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
        segments=segments if voice_mode in {"edge", "openai"} else [],
        duration=duration,
        voice_mode=voice_mode,
        voice=voice_voice,
        voice_lang=voice_lang,
        work_dir=work_dir,
    )

    if not bgm_path:
        return narration

    bgm = Path(bgm_path)
    if not bgm.exists():
        raise ValidationError(f"BGM file not found: {bgm}")

    narration_ranges = [(seg.start, seg.end) for seg in segments if _has_narration(seg)]
    has_narration = bool(narration_ranges and voice_mode != "none")
    duck_gain = 10 ** ((-12 if has_narration else -10) / 20)
    volume_expr = _build_duck_volume_expression(
        narration_ranges=narration_ranges,
        duck_gain=duck_gain,
        fade=_clamp(fade, 0.0, 0.5),
    )

    mixed = work_dir / "audio_mix.wav"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(bgm),
        "-i",
        str(narration.track_path),
        "-filter_complex",
        (
            f"[0:a]atrim=0:{duration:.3f},asetpts=N/SR/TB,volume='{volume_expr}'[bgm];"
            f"[1:a]atrim=0:{duration:.3f},asetpts=N/SR/TB[narr];"
            "[bgm][narr]amix=inputs=2:normalize=0[mix]"
        ),
        "-map",
        "[mix]",
        "-c:a",
        "pcm_s16le",
        str(mixed),
    ]
    run_command(cmd)

    return NarrationResult(track_path=mixed, warnings=narration.warnings)


def mux_audio_with_video(
    ffmpeg_bin: str,
    input_video: Path,
    audio_track: Path,
    output_video: Path,
) -> None:
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_video),
        "-i",
        str(audio_track),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_video),
    ]
    run_command(cmd)
