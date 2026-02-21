from __future__ import annotations

from pathlib import Path
import textwrap

from .script_parser import Segment
from .utils import ValidationError, run_command


def _ass_time(seconds: float) -> str:
    if seconds < 0:
        raise ValidationError("Subtitle timestamp must be >= 0")
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _apply_emphasis_markup(text: str, base_font_size: int) -> str:
    """Approximate {emphasis} by applying larger ASS font override tags."""
    if "{" not in text or "}" not in text:
        return _escape_ass_text(text)

    emphasis_size = int(base_font_size * 1.25)
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            close = text.find("}", i + 1)
            if close == -1:
                out.append(_escape_ass_text(text[i:]))
                break
            chunk = _escape_ass_text(text[i + 1 : close])
            out.append(rf"{{\fs{emphasis_size}}}{chunk}{{\r}}")
            i = close + 1
        else:
            next_open = text.find("{", i)
            if next_open == -1:
                out.append(_escape_ass_text(text[i:]))
                break
            out.append(_escape_ass_text(text[i:next_open]))
            i = next_open
    return "".join(out)


def _wrap_subtitle(text: str, width: int, font_size: int) -> str:
    max_px = int(width * 0.8)
    avg_char_px = max(1, int(font_size * 0.55))
    max_chars = max(10, max_px // avg_char_px)
    wrapped = textwrap.wrap(text, width=max_chars, break_long_words=False, break_on_hyphens=False)
    return "\\N".join(wrapped) if wrapped else text


def _ffmpeg_filter_escape(path: Path) -> str:
    value = path.resolve().as_posix()
    value = value.replace("'", r"\'")
    if len(value) >= 2 and value[1] == ":":
        value = f"{value[0]}\\:{value[2:]}"
    return value


def generate_ass_subtitles(
    segments: list[Segment],
    out_path: str | Path,
    size: tuple[int, int],
    subtitle_pos: str,
    safe_margin: float,
) -> Path:
    width, height = size
    if subtitle_pos not in {"bottom", "center"}:
        raise ValidationError("--subtitle-pos must be 'bottom' or 'center'")

    margin_v = max(10, int(height * safe_margin))
    alignment = 2 if subtitle_pos == "bottom" else 5
    font_size = max(28, int(height * 0.045))
    outline = max(2, int(font_size * 0.08))
    shadow = max(1, int(font_size * 0.05))

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,"
        "StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,"
        f"{outline},{shadow},{alignment},40,40,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]

    for seg in segments:
        if not seg.subtitle:
            continue
        wrapped = _wrap_subtitle(seg.subtitle.strip(), width=width, font_size=font_size)
        styled = _apply_emphasis_markup(wrapped, base_font_size=font_size)
        start = _ass_time(seg.start)
        end = _ass_time(seg.end)
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{styled}")

    output = Path(out_path)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def apply_subtitles_to_video(ffmpeg_bin: str, input_video: Path, ass_path: Path, output_video: Path) -> None:
    escaped_ass = _ffmpeg_filter_escape(ass_path)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_video),
        "-vf",
        f"subtitles='{escaped_ass}'",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        str(output_video),
    ]
    try:
        run_command(cmd)
    except Exception as exc:  # normalize to friendly error
        message = str(exc)
        if "subtitles" in message.lower() or "libass" in message.lower() or "No such filter" in message:
            raise ValidationError(
                "FFmpeg subtitles filter is unavailable. Install FFmpeg with libass support "
                "(the 'subtitles' filter) and retry."
            ) from exc
        raise
