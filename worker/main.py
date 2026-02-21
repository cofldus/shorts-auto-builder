from __future__ import annotations

import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
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
    tone: str = "Calm and immersive"
    duration: float = 30.0
    style: str = "cinematic vertical short"
    voice: str = Field(default="edge", pattern="^(none|edge|openai|piper)$")
    image_motion: str = Field(default="slow", pattern="^(none|slow)$")
    generation_mode: str = Field(
        default="mock",
        pattern="^(mock|openai_image|external_video)$",
    )


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
                f"subtitle: {topic} scene {idx + 1}",
                f"narration: {tone} mood. {topic} in scene {idx + 1}.",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _build_scene_prompts(topic: str, tone: str, style: str, count: int) -> list[str]:
    prompts: list[str] = []
    for idx in range(count):
        prompts.append(
            f"Vertical 9:16 scene {idx + 1} about {topic}. "
            f"Tone: {tone}. Style: {style}. Realistic texture and natural light."
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
        raise HTTPException(status_code=500, detail="openai package is required") from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is required")

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
            raise HTTPException(status_code=500, detail="empty image generation response")

        image_path = assets_dir / f"ai_scene_{idx + 1:02d}.png"
        image_path.write_bytes(base64.b64decode(image_b64))
        generated.append(image_path)
    return generated


def _generate_external_video_assets(
    assets_dir: Path,
    topic: str,
    tone: str,
    style: str,
    count: int,
) -> list[Path]:
    try:
        import requests
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="requests package is required") from exc

    base_url = os.getenv("VIDEO_PROVIDER_API_BASE", "").rstrip("/")
    api_key = os.getenv("VIDEO_PROVIDER_API_KEY", "")
    create_path = os.getenv("VIDEO_PROVIDER_CREATE_PATH", "/v1/video/jobs")
    status_path = os.getenv("VIDEO_PROVIDER_STATUS_PATH", "/v1/video/jobs/{job_id}")
    poll_interval = float(os.getenv("VIDEO_PROVIDER_POLL_SEC", "2"))
    poll_max = int(os.getenv("VIDEO_PROVIDER_POLL_MAX", "45"))

    if not base_url or not api_key:
        raise HTTPException(
            status_code=400,
            detail="VIDEO_PROVIDER_API_BASE and VIDEO_PROVIDER_API_KEY are required",
        )

    prompts = _build_scene_prompts(topic=topic, tone=tone, style=style, count=count)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    generated: list[Path] = []

    for idx, prompt in enumerate(prompts):
        create_url = f"{base_url}{create_path}"
        create_resp = requests.post(
            create_url,
            headers=headers,
            json={"prompt": prompt, "aspect_ratio": "9:16", "duration": 5},
            timeout=60,
        )
        if create_resp.status_code >= 300:
            raise HTTPException(
                status_code=502,
                detail=f"provider create failed: {create_resp.status_code} {create_resp.text[:300]}",
            )

        create_data = create_resp.json()
        video_url = create_data.get("video_url")
        job_id = create_data.get("id") or create_data.get("job_id")

        if not video_url and not job_id:
            raise HTTPException(status_code=502, detail="provider response missing video_url/job_id")

        if not video_url:
            for _ in range(poll_max):
                poll_url = f"{base_url}{status_path.format(job_id=job_id)}"
                poll_resp = requests.get(poll_url, headers=headers, timeout=60)
                if poll_resp.status_code >= 300:
                    raise HTTPException(
                        status_code=502,
                        detail=f"provider poll failed: {poll_resp.status_code} {poll_resp.text[:300]}",
                    )
                poll_data = poll_resp.json()
                status = str(poll_data.get("status", "")).lower()
                if status in {"succeeded", "completed", "done"}:
                    video_url = poll_data.get("video_url")
                    break
                if status in {"failed", "error", "canceled"}:
                    raise HTTPException(status_code=502, detail=f"provider job failed: {poll_data}")
                time.sleep(poll_interval)

        if not video_url:
            raise HTTPException(status_code=504, detail="provider polling timed out")

        out = assets_dir / f"provider_scene_{idx + 1:02d}.mp4"
        video_resp = requests.get(video_url, timeout=120)
        if video_resp.status_code >= 300:
            raise HTTPException(
                status_code=502,
                detail=f"provider video download failed: {video_resp.status_code}",
            )
        out.write_bytes(video_resp.content)
        generated.append(out)

    return generated


def _to_public_url(path: Path) -> str | None:
    public_base = os.getenv("WORKER_PUBLIC_BASE_URL", "").rstrip("/")
    if not public_base:
        return None
    return f"{public_base}/{path.as_posix()}"


def _upload_to_s3(local_file: Path, object_key: str) -> str:
    try:
        import boto3
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="boto3 package is required for S3 upload") from exc

    bucket = os.getenv("S3_BUCKET", "")
    region = os.getenv("S3_REGION", "")
    endpoint = os.getenv("S3_ENDPOINT_URL", "")
    public_base = os.getenv("S3_PUBLIC_BASE_URL", "").rstrip("/")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET is required")

    kwargs: dict[str, str] = {}
    if region:
        kwargs["region_name"] = region
    if endpoint:
        kwargs["endpoint_url"] = endpoint

    s3 = boto3.client("s3", **kwargs)
    extra_args = {"ContentType": "video/mp4"}
    s3.upload_file(str(local_file), bucket, object_key, ExtraArgs=extra_args)

    if public_base:
        return f"{public_base}/{object_key}"
    if endpoint:
        return f"{endpoint.rstrip('/')}/{bucket}/{object_key}"
    if region:
        return f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}"
    return f"https://{bucket}.s3.amazonaws.com/{object_key}"


def _publish_output(output_dir: Path, local_mp4: Path, filename: str) -> dict[str, str]:
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    saved_path = output_dir / filename
    shutil.copy2(local_mp4, saved_path)

    result = {"output_path": str(saved_path)}
    if backend == "s3":
        prefix = os.getenv("S3_PREFIX", "shorts").strip("/")
        object_key = f"{prefix}/{filename}" if prefix else filename
        result["output_url"] = _upload_to_s3(saved_path, object_key)
    else:
        public_url = _to_public_url(saved_path)
        if public_url:
            result["output_url"] = public_url
    return result


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

    output_dir = _resolve_output_dir()
    filename = f"{uuid4().hex}.mp4"

    with tempfile.TemporaryDirectory(prefix="worker_render_") as tmp_dir:
        tmp = Path(tmp_dir)
        temp_output = tmp / "output.mp4"
        completed = _run_render(
            script_path=script,
            assets_path=assets,
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
        published = _publish_output(output_dir, temp_output, filename)

    return {"ok": True, **published}


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
    filename = f"{job_id}.mp4"

    with tempfile.TemporaryDirectory(prefix="worker_job_") as tmp_dir:
        tmp = Path(tmp_dir)
        script_path = tmp / "script.txt"
        assets_dir = tmp / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text, encoding="utf-8")

        for idx, file in enumerate(media):
            filename_part = Path(file.filename or f"file_{idx}").name
            target = assets_dir / f"{idx:04d}_{filename_part}"
            target.write_bytes(await file.read())

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
        published = _publish_output(output_dir, temp_output, filename)

    return {"ok": True, "jobId": job_id, **published, "message": "render completed"}


@app.post("/generate-creative")
def generate_creative(req: CreativeRequest):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic is empty")

    output_dir = _resolve_output_dir()
    job_id = uuid4().hex
    filename = f"creative_{job_id}.mp4"
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
        elif req.generation_mode == "external_video":
            generated_assets = _generate_external_video_assets(
                assets_dir=assets_dir,
                topic=req.topic,
                tone=req.tone,
                style=req.style,
                count=scene_count,
            )
        else:
            generated_assets = _generate_mock_assets(
                ffmpeg_bin=_resolve_ffmpeg_bin(),
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
        published = _publish_output(output_dir, temp_output, filename)

    return {
        "ok": True,
        "jobId": job_id,
        **published,
        "mode": req.generation_mode,
        "asset_count": len(generated_assets),
        "script_preview": script_text.splitlines()[:8],
        "message": "creative render completed",
    }
