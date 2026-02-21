from __future__ import annotations

import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

app = FastAPI(title="shorts-render-worker")


class RenderRequest(BaseModel):
    script_path: str
    assets_path: str
    output_path: str = "output_from_worker.mp4"
    voice: str = Field(default="none", pattern="^(none|edge|openai|piper)$")
    duration: float = 30.0
    image_motion: str = Field(default="none", pattern="^(none|slow)$")


class CreativeRequest(BaseModel):
    topic: str
    tone: str = "담백하고 몰입감 있는 톤"
    duration: float = 30.0
    style: str = "cinematic vertical short"
    voice: str = Field(default="edge", pattern="^(none|edge|openai|piper)$")
    image_motion: str = Field(default="slow", pattern="^(none|slow)$")
    generation_mode: str = Field(default="mock", pattern="^(mock|openai_image)$")


def _run_render(
    script_path: Path,
    assets_path: Path,
    output_path: Path,
    voice: str,
    duration: float,
    image_motion: str,
    voice_lang: str,
    voice_voice: str,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        "python",
        "-m",
        "shorts_maker",
        "--script",
        str(script_path),
        "--assets",
        str(assets_path),
        "--out",
        str(output_path),
        "--voice",
        voice,
        "--duration",
        str(duration),
        "--image-motion",
        image_motion,
        "--voice-lang",
        voice_lang,
        "--voice-voice",
        voice_voice,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def _resolve_output_dir() -> Path:
    output_dir = Path(os.getenv("WORKER_OUTPUT_DIR", "worker_outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _resolve_ffmpeg_bin() -> str:
    configured = os.getenv("FFMPEG_BIN")
    if configured and (shutil.which(configured) or Path(configured).exists()):
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = sorted(root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"), reverse=True)
        if matches:
            return str(matches[0])
    return "ffmpeg"


def _build_script(topic: str, tone: str, duration: float) -> str:
    segments = 5
    step = duration / segments
    lines: list[str] = []
    for idx in range(segments):
        start = idx * step
        end = duration if idx == segments - 1 else (idx + 1) * step
        lines.extend(
            [
                f"start: {start:.1f}",
                f"end: {end:.1f}",
                f"subtitle: {topic} - 장면 {idx + 1}",
                f"narration: {tone} 분위기로 {topic}를 장면 {idx + 1}에서 전달합니다.",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _build_scene_prompts(topic: str, tone: str, style: str, count: int) -> list[str]:
    prompts: list[str] = []
    for idx in range(count):
        prompts.append(
            f"Vertical 9:16 cinematic scene {idx + 1} about {topic}. "
            f"Tone: {tone}. Visual style: {style}. High detail, natural lighting, realistic texture."
        )
    return prompts


def _generate_mock_assets(ffmpeg_bin: str, assets_dir: Path, duration: float, count: int) -> list[Path]:
    palette = ["#1f2937", "#0f766e", "#7c2d12", "#4c1d95", "#075985", "#3f3f46"]
    per_clip = max(2.0, duration / count)
    generated: list[Path] = []
    for idx in range(count):
        out = assets_dir / f"mock_scene_{idx + 1:02d}.mp4"
        color = palette[idx % len(palette)]
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1080x1920:r=30",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t",
            f"{per_clip:.2f}",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            str(out),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={"stderr": completed.stderr[-2000:], "stdout": completed.stdout[-2000:]},
            )
        generated.append(out)
    return generated


def _generate_openai_image_assets(
    assets_dir: Path,
    topic: str,
    tone: str,
    style: str,
    count: int,
) -> list[Path]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="openai 패키지가 필요합니다.") from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 필요합니다.")

    model_name = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
    client = OpenAI(api_key=api_key)

    prompts = _build_scene_prompts(topic=topic, tone=tone, style=style, count=count)
    generated: list[Path] = []
    for idx, prompt in enumerate(prompts):
        response = client.images.generate(model=model_name, prompt=prompt, size="1024x1536")
        image_b64 = None
        if response.data and len(response.data) > 0:
            image_b64 = getattr(response.data[0], "b64_json", None)
        if not image_b64:
            raise HTTPException(status_code=500, detail="이미지 생성 응답이 비어 있습니다.")

        image_path = assets_dir / f"ai_scene_{idx + 1:02d}.png"
        image_path.write_bytes(base64.b64decode(image_b64))
        generated.append(image_path)

    return generated


@app.get("/health")
def health_check():
    return {"ok": True}


@app.post("/render")
def render_video(req: RenderRequest):
    script = Path(req.script_path)
    assets = Path(req.assets_path)

    if not script.exists():
        raise HTTPException(status_code=400, detail=f"script_path not found: {script}")
    if not assets.exists() or not assets.is_dir():
        raise HTTPException(status_code=400, detail=f"assets_path not found: {assets}")

    output = Path(req.output_path)
    completed = _run_render(
        script_path=script,
        assets_path=assets,
        output_path=output,
        voice=req.voice,
        duration=req.duration,
        image_motion=req.image_motion,
        voice_lang="ko-KR",
        voice_voice="ko-KR-SunHiNeural",
    )
    if completed.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={"stderr": completed.stderr[-4000:], "stdout": completed.stdout[-4000:]},
        )

    return {
        "ok": True,
        "output_path": str(output),
        "stdout": completed.stdout[-2000:],
    }


@app.post("/render-upload")
async def render_upload(
    script_text: str = Form(...),
    voice: str = Form("none"),
    duration: float = Form(30.0),
    image_motion: str = Form("none"),
    voice_lang: str = Form("ko-KR"),
    voice_voice: str = Form("ko-KR-SunHiNeural"),
    media: list[UploadFile] = File(...),
):
    if not script_text.strip():
        raise HTTPException(status_code=400, detail="script_text is empty")
    if voice not in {"none", "edge", "openai", "piper"}:
        raise HTTPException(status_code=400, detail="invalid voice")
    if image_motion not in {"none", "slow"}:
        raise HTTPException(status_code=400, detail="invalid image_motion")
    if not media:
        raise HTTPException(status_code=400, detail="no media files")

    output_dir = _resolve_output_dir()
    job_id = uuid4().hex
    final_output = output_dir / f"{job_id}.mp4"

    with tempfile.TemporaryDirectory(prefix="worker_job_") as tmp_dir:
        tmp = Path(tmp_dir)
        script_path = tmp / "script.txt"
        assets_dir = tmp / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        script_path.write_text(script_text, encoding="utf-8")

        for idx, file in enumerate(media):
            filename = Path(file.filename or f"file_{idx}").name
            target = assets_dir / f"{idx:04d}_{filename}"
            content = await file.read()
            target.write_bytes(content)

        temp_output = tmp / "output.mp4"
        completed = _run_render(
            script_path=script_path,
            assets_path=assets_dir,
            output_path=temp_output,
            voice=voice,
            duration=duration,
            image_motion=image_motion,
            voice_lang=voice_lang,
            voice_voice=voice_voice,
        )
        if completed.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={"stderr": completed.stderr[-4000:], "stdout": completed.stdout[-4000:]},
            )

        shutil.copy2(temp_output, final_output)

    return {
        "ok": True,
        "jobId": job_id,
        "output_path": str(final_output),
        "message": "렌더링이 완료되었습니다.",
    }


@app.post("/generate-creative")
def generate_creative(req: CreativeRequest):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic is empty")

    output_dir = _resolve_output_dir()
    job_id = uuid4().hex
    final_output = output_dir / f"creative_{job_id}.mp4"

    ffmpeg_bin = _resolve_ffmpeg_bin()
    scene_count = 6

    with tempfile.TemporaryDirectory(prefix="worker_creative_") as tmp_dir:
        tmp = Path(tmp_dir)
        script_path = tmp / "script.txt"
        assets_dir = tmp / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        script_text = _build_script(topic=req.topic, tone=req.tone, duration=req.duration)
        script_path.write_text(script_text, encoding="utf-8")

        if req.generation_mode == "openai_image":
            generated_assets = _generate_openai_image_assets(
                assets_dir=assets_dir,
                topic=req.topic,
                tone=req.tone,
                style=req.style,
                count=scene_count,
            )
        else:
            generated_assets = _generate_mock_assets(
                ffmpeg_bin=ffmpeg_bin,
                assets_dir=assets_dir,
                duration=req.duration,
                count=scene_count,
            )

        temp_output = tmp / "output.mp4"
        completed = _run_render(
            script_path=script_path,
            assets_path=assets_dir,
            output_path=temp_output,
            voice=req.voice,
            duration=req.duration,
            image_motion=req.image_motion,
            voice_lang="ko-KR",
            voice_voice="ko-KR-SunHiNeural",
        )
        if completed.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={"stderr": completed.stderr[-4000:], "stdout": completed.stdout[-4000:]},
            )

        shutil.copy2(temp_output, final_output)

    return {
        "ok": True,
        "jobId": job_id,
        "output_path": str(final_output),
        "mode": req.generation_mode,
        "asset_count": len(generated_assets),
        "script_preview": script_text.splitlines()[:8],
        "message": "생성형 영상 렌더링이 완료되었습니다.",
    }
