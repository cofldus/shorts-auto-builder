from __future__ import annotations

from pathlib import Path
import tempfile

from .assets import is_video, scan_assets, select_assets_for_segments
from .audio import build_final_audio_track, mux_audio_with_video
from .script_parser import Segment
from .subtitles import apply_subtitles_to_video, generate_ass_subtitles
from .utils import ValidationError, media_has_audio_stream, preflight_check, run_command


def _build_size_filters(size: tuple[int, int]) -> str:
    width, height = size
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )


def _render_black_segment(
    ffmpeg_bin: str,
    out_path: Path,
    duration: float,
    size: tuple[int, int],
    fps: int,
) -> None:
    width, height = size
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:r={fps}",
        "-f",
        "lavfi",
        "-t",
        f"{duration}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-shortest",
        "-t",
        f"{duration}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(out_path),
    ]
    run_command(cmd)


def _render_video_segment(
    ffmpeg_bin: str,
    ffprobe_bin: str,
    source: Path,
    out_path: Path,
    duration: float,
    size: tuple[int, int],
    fps: int,
) -> None:
    vf = _build_size_filters(size)
    if media_has_audio_stream(ffprobe_bin, source):
        cmd = [
            ffmpeg_bin,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-shortest",
            "-t",
            f"{duration}",
            "-vf",
            vf,
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out_path),
        ]
    else:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-t",
            f"{duration}",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-shortest",
            "-t",
            f"{duration}",
            "-vf",
            vf,
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out_path),
        ]
    run_command(cmd)


def _render_image_segment(
    ffmpeg_bin: str,
    source: Path,
    out_path: Path,
    duration: float,
    size: tuple[int, int],
    fps: int,
    image_motion: str,
) -> None:
    width, height = size
    if image_motion == "slow":
        frames = max(1, int(duration * fps))
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='min(zoom+0.0004,1.05)':"
            f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )
    else:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
    cmd = [
        ffmpeg_bin,
        "-y",
        "-loop",
        "1",
        "-i",
        str(source),
        "-f",
        "lavfi",
        "-t",
        f"{duration}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-shortest",
        "-t",
        f"{duration}",
        "-vf",
        vf,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(out_path),
    ]
    run_command(cmd)


def _render_segment_clip(
    ffmpeg_bin: str,
    ffprobe_bin: str,
    asset: Path,
    out_path: Path,
    duration: float,
    size: tuple[int, int],
    fps: int,
    image_motion: str,
) -> None:
    if is_video(asset):
        _render_video_segment(ffmpeg_bin, ffprobe_bin, asset, out_path, duration, size, fps)
    else:
        _render_image_segment(ffmpeg_bin, asset, out_path, duration, size, fps, image_motion)


def _concat_clips(ffmpeg_bin: str, clip_paths: list[Path], output_path: Path) -> None:
    concat_file = output_path.with_suffix(".concat.txt")
    concat_file.write_text(
        "\n".join(f"file '{path.as_posix()}'" for path in clip_paths),
        encoding="utf-8",
    )
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output_path),
    ]
    run_command(cmd)
    concat_file.unlink(missing_ok=True)


def render_video(
    segments: list[Segment],
    assets_dir: str | Path,
    out_path: str | Path,
    size: tuple[int, int],
    fps: int,
    seed: int,
    duration: float,
    subtitle_pos: str,
    safe_margin: float,
    bgm: str | None,
    voice: str,
    voice_lang: str,
    voice_voice: str,
    font: str | None = None,
    fade: float = 0.15,
    image_motion: str = "none",
) -> None:
    del font  # reserved for future ass style customization
    if duration <= 0:
        raise ValidationError("Duration must be greater than 0")

    subtitles_enabled = any(bool(seg.subtitle and seg.subtitle.strip()) for seg in segments)
    ffmpeg_bin, ffprobe_bin = preflight_check(subtitles_enabled=subtitles_enabled)
    pools = scan_assets(assets_dir)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="shorts_maker_") as tmp_dir:
        tmp = Path(tmp_dir)
        clips: list[Path] = []
        timeline_pos = 0.0
        chosen_assets = select_assets_for_segments(pools, segment_count=len(segments), seed=seed)

        for i, segment in enumerate(segments):
            if segment.start > timeline_pos:
                gap = segment.start - timeline_pos
                if gap > 0:
                    gap_clip = tmp / f"clip_gap_{i:04d}.mp4"
                    _render_black_segment(ffmpeg_bin, gap_clip, gap, size, fps)
                    clips.append(gap_clip)
                timeline_pos = segment.start

            seg_dur = min(segment.duration, max(0.0, duration - timeline_pos))
            if seg_dur <= 0:
                continue

            asset = chosen_assets[i]
            seg_clip = tmp / f"clip_seg_{i:04d}.mp4"
            _render_segment_clip(
                ffmpeg_bin,
                ffprobe_bin,
                asset,
                seg_clip,
                seg_dur,
                size,
                fps,
                image_motion,
            )
            clips.append(seg_clip)
            timeline_pos += seg_dur

            if timeline_pos >= duration:
                break

        if timeline_pos < duration:
            tail = duration - timeline_pos
            tail_clip = tmp / "clip_tail.mp4"
            _render_black_segment(ffmpeg_bin, tail_clip, tail, size, fps)
            clips.append(tail_clip)

        base_video = tmp / "base.mp4"
        _concat_clips(ffmpeg_bin, clips, base_video)

        subtitle_video = tmp / "subtitled.mp4"
        if subtitles_enabled:
            ass_path = tmp / "subtitles.ass"
            generate_ass_subtitles(
                segments=segments,
                out_path=ass_path,
                size=size,
                subtitle_pos=subtitle_pos,
                safe_margin=safe_margin,
            )
            apply_subtitles_to_video(ffmpeg_bin, base_video, ass_path, subtitle_video)
        else:
            subtitle_video = base_video

        if voice == "none" and not bgm:
            print(
                "[warning] --voice none 이고 --bgm이 없으면 내레이션/배경음이 없어 결과가 무음일 수 있습니다."
            )
            run_command(
                [
                    ffmpeg_bin,
                    "-y",
                    "-i",
                    str(subtitle_video),
                    "-c",
                    "copy",
                    str(out),
                ]
            )
            return

        audio_result = build_final_audio_track(
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
            segments=segments,
            duration=duration,
            voice_mode=voice,
            voice_lang=voice_lang,
            voice_voice=voice_voice,
            bgm_path=bgm,
            fade=fade,
            work_dir=tmp,
        )
        for warning in audio_result.warnings:
            print(f"[warning] {warning}")

        mux_audio_with_video(
            ffmpeg_bin=ffmpeg_bin,
            input_video=subtitle_video,
            audio_track=audio_result.track_path,
            output_video=out,
        )
