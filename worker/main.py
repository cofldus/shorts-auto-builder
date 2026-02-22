from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field


def _load_dotenv_file() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip()
        if not key:
            continue
        if key in os.environ and os.environ[key]:
            continue
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        os.environ[key] = value


_load_dotenv_file()

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
        pattern="^(mock|openai_image|external_video|replicate_video)$",
    )


def _resolve_output_dir() -> Path:
    output_dir = Path(os.getenv("WORKER_OUTPUT_DIR", "worker_outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _use_env_proxy() -> bool:
    return os.getenv("OUTBOUND_USE_ENV_PROXY", "0").lower() in {"1", "true", "yes"}


def _jobs_dir(output_dir: Path) -> Path:
    jobs = output_dir / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    return jobs


def _job_file(output_dir: Path, job_id: str) -> Path:
    return _jobs_dir(output_dir) / f"{job_id}.json"


def _job_update(output_dir: Path, job_id: str, payload: dict) -> None:
    path = _job_file(output_dir, job_id)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data.update(payload)
    data["job_id"] = job_id
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _job_read(output_dir: Path, job_id: str) -> dict:
    path = _job_file(output_dir, job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="job not found")
    return json.loads(path.read_text(encoding="utf-8"))


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


def _normalize_script_text(raw: str) -> str:
    allowed = {"start", "end", "subtitle", "narration"}
    pairs: list[tuple[str, str]] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("```"):
            continue
        if ":" not in s:
            continue
        key, value = s.split(":", 1)
        key_norm = key.strip().lower().lstrip("\ufeff")
        if key_norm not in allowed:
            continue
        pairs.append((key_norm, value.strip()))

    segments: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for key, value in pairs:
        if key == "start":
            if "start" in current and "end" in current:
                segments.append(current)
            current = {"start": value}
            continue
        if "start" not in current:
            continue
        current[key] = value

    if "start" in current and "end" in current:
        segments.append(current)

    if not segments:
        raise HTTPException(
            status_code=400,
            detail="script 형식이 올바르지 않습니다. start/end가 포함된 세그먼트를 확인하세요.",
        )

    lines: list[str] = []
    for seg in segments:
        lines.append(f"start: {seg['start']}")
        lines.append(f"end: {seg['end']}")
        if seg.get("subtitle"):
            lines.append(f"subtitle: {seg['subtitle']}")
        if seg.get("narration"):
            lines.append(f"narration: {seg['narration']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _parse_time_to_seconds(value: str) -> float | None:
    s = value.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass

    parts = s.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None

    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return None


def _script_max_end_seconds(script_text: str) -> float:
    max_end = 0.0
    for line in script_text.splitlines():
        s = line.strip()
        if not s.lower().startswith("end:"):
            continue
        _, value = s.split(":", 1)
        sec = _parse_time_to_seconds(value)
        if sec is not None and sec > max_end:
            max_end = sec
    return max_end


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
        import httpx
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="openai/httpx package is required") from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is required")

    model_name = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
    client = OpenAI(api_key=api_key, http_client=httpx.Client(trust_env=_use_env_proxy(), timeout=120))

    prompts = _build_scene_prompts(topic=topic, tone=tone, style=style, count=count)
    generated: list[Path] = []
    for idx, prompt in enumerate(prompts):
        try:
            response = client.images.generate(model=model_name, prompt=prompt, size="1024x1536")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"openai image request failed: {exc}") from exc
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

    session = requests.Session()
    session.trust_env = _use_env_proxy()

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
        try:
            create_resp = session.post(
                create_url,
                headers=headers,
                json={"prompt": prompt, "aspect_ratio": "9:16", "duration": 5},
                timeout=60,
            )
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"provider request failed: {exc}") from exc
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
                try:
                    poll_resp = session.get(poll_url, headers=headers, timeout=60)
                except requests.RequestException as exc:
                    raise HTTPException(status_code=502, detail=f"provider poll request failed: {exc}") from exc
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
        try:
            video_resp = session.get(video_url, timeout=120)
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"provider video download request failed: {exc}") from exc
        if video_resp.status_code >= 300:
            raise HTTPException(
                status_code=502,
                detail=f"provider video download failed: {video_resp.status_code}",
            )
        out.write_bytes(video_resp.content)
        generated.append(out)

    return generated


def _generate_replicate_video_assets(
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

    session = requests.Session()
    session.trust_env = _use_env_proxy()

    token = os.getenv("REPLICATE_API_TOKEN", "")
    model = os.getenv("REPLICATE_MODEL", "kwaivgi/kling-v1.6-pro")
    version = os.getenv("REPLICATE_VERSION", "")
    poll_interval = float(os.getenv("REPLICATE_POLL_SEC", "2"))
    poll_max = int(os.getenv("REPLICATE_POLL_MAX", "60"))

    if not token:
        raise HTTPException(status_code=400, detail="REPLICATE_API_TOKEN is required")

    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }
    prompts = _build_scene_prompts(topic=topic, tone=tone, style=style, count=count)
    generated: list[Path] = []

    for idx, prompt in enumerate(prompts):
        payload: dict = {"input": {"prompt": prompt, "aspect_ratio": "9:16"}}
        if version:
            payload["version"] = version
            create_url = "https://api.replicate.com/v1/predictions"
        else:
            create_url = f"https://api.replicate.com/v1/models/{model}/predictions"

        try:
            create_resp = session.post(create_url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"replicate request failed: {exc}") from exc
        if create_resp.status_code >= 300:
            raise HTTPException(
                status_code=502,
                detail=f"replicate create failed: {create_resp.status_code} {create_resp.text[:300]}",
            )

        pred = create_resp.json()
        pred_id = pred.get("id")
        if not pred_id:
            raise HTTPException(status_code=502, detail="replicate response missing prediction id")

        final = pred
        for _ in range(poll_max):
            status = str(final.get("status", "")).lower()
            if status in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(poll_interval)
            try:
                poll_resp = session.get(
                    f"https://api.replicate.com/v1/predictions/{pred_id}",
                    headers=headers,
                    timeout=120,
                )
            except requests.RequestException as exc:
                raise HTTPException(status_code=502, detail=f"replicate poll request failed: {exc}") from exc
            if poll_resp.status_code >= 300:
                raise HTTPException(
                    status_code=502,
                    detail=f"replicate poll failed: {poll_resp.status_code} {poll_resp.text[:300]}",
                )
            final = poll_resp.json()

        if str(final.get("status", "")).lower() != "succeeded":
            raise HTTPException(status_code=502, detail=f"replicate prediction failed: {final}")

        output = final.get("output")
        video_url = None
        if isinstance(output, str):
            video_url = output
        elif isinstance(output, list) and output:
            if isinstance(output[0], str):
                video_url = output[0]
            elif isinstance(output[0], dict):
                video_url = output[0].get("url") or output[0].get("video")
        elif isinstance(output, dict):
            video_url = output.get("url") or output.get("video")

        if not video_url:
            raise HTTPException(status_code=502, detail="replicate output missing video url")

        out = assets_dir / f"replicate_scene_{idx + 1:02d}.mp4"
        try:
            video_resp = session.get(video_url, timeout=120)
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"replicate video download request failed: {exc}") from exc
        if video_resp.status_code >= 300:
            raise HTTPException(
                status_code=502,
                detail=f"replicate video download failed: {video_resp.status_code}",
            )
        out.write_bytes(video_resp.content)
        generated.append(out)

    return generated


def _has_external_video_env() -> bool:
    return bool(os.getenv("VIDEO_PROVIDER_API_BASE") and os.getenv("VIDEO_PROVIDER_API_KEY"))


def _has_replicate_env() -> bool:
    return bool(os.getenv("REPLICATE_API_TOKEN"))


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
    url_mode = os.getenv("S3_URL_MODE", "public").lower()
    presigned_exp = int(os.getenv("S3_PRESIGNED_EXPIRES", "3600"))
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET is required")

    kwargs: dict[str, str] = {}
    if region:
        kwargs["region_name"] = region
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    use_env_proxy = os.getenv("S3_USE_ENV_PROXY", "0").lower() in {"1", "true", "yes"}
    if not use_env_proxy:
        try:
            from botocore.config import Config as BotoConfig

            kwargs["config"] = BotoConfig(proxies={})
        except Exception:
            pass

    try:
        s3 = boto3.client("s3", **kwargs)
        s3.upload_file(str(local_file), bucket, object_key, ExtraArgs={"ContentType": "video/mp4"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"S3 upload failed: {exc}") from exc

    if url_mode == "presigned":
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=presigned_exp,
        )
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


def _run_pipeline(
    *,
    job_id: str,
    script_text: str,
    assets_builder,
    voice: str,
    duration: float,
    image_motion: str,
    voice_lang: str,
    voice_voice: str,
    mode: str,
) -> dict:
    output_dir = _resolve_output_dir()
    _job_update(output_dir, job_id, {"status": "processing", "mode": mode})

    try:
        with tempfile.TemporaryDirectory(prefix="worker_job_") as tmp_dir:
            tmp = Path(tmp_dir)
            script_path = tmp / "script.txt"
            assets_dir = tmp / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            script_path.write_text(script_text, encoding="utf-8")

            generated_assets = assets_builder(assets_dir)
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
                _job_update(
                    output_dir,
                    job_id,
                    {
                        "status": "failed",
                        "error": (completed.stderr or completed.stdout or "render failed")[-2000:],
                    },
                )
                raise HTTPException(
                    status_code=500,
                    detail={"stderr": completed.stderr[-4000:], "stdout": completed.stdout[-4000:]},
                )
            try:
                published = _publish_output(output_dir, temp_output, f"{job_id}.mp4")
            except HTTPException as exc:
                _job_update(
                    output_dir,
                    job_id,
                    {"status": "failed", "error": str(exc.detail)[:2000]},
                )
                raise
            except Exception as exc:
                _job_update(
                    output_dir,
                    job_id,
                    {"status": "failed", "error": str(exc)[:2000]},
                )
                raise HTTPException(status_code=500, detail=f"output publish failed: {exc}") from exc

        payload = {"status": "completed", **published, "asset_count": len(generated_assets)}
        _job_update(output_dir, job_id, payload)
        return payload
    except HTTPException as exc:
        existing = _job_read(output_dir, job_id)
        if existing.get("status") != "failed":
            _job_update(
                output_dir,
                job_id,
                {
                    "status": "failed",
                    "error": str(exc.detail)[:2000],
                },
            )
        raise
    except Exception as exc:
        _job_update(
            output_dir,
            job_id,
            {"status": "failed", "error": str(exc)[:2000]},
        )
        raise HTTPException(status_code=500, detail=f"pipeline failed: {exc}") from exc


@app.get("/health")
def health_check():
    return {"ok": True}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    output_dir = _resolve_output_dir()
    return {"ok": True, **_job_read(output_dir, job_id)}


@app.post("/render")
def render_video(req: RenderRequest):
    script = Path(req.script_path)
    assets = Path(req.assets_path)
    if not script.exists():
        raise HTTPException(status_code=400, detail=f"script_path not found: {script}")
    if not assets.exists() or not assets.is_dir():
        raise HTTPException(status_code=400, detail=f"assets_path not found: {assets}")

    output_dir = _resolve_output_dir()
    job_id = uuid4().hex
    _job_update(output_dir, job_id, {"status": "queued", "mode": "render"})

    def assets_builder(dst: Path):
        created: list[Path] = []
        for idx, p in enumerate(sorted(assets.iterdir())):
            if p.is_file():
                out = dst / f"{idx:04d}_{p.name}"
                shutil.copy2(p, out)
                created.append(out)
        return created

    result = _run_pipeline(
        job_id=job_id,
        script_text=script.read_text(encoding="utf-8"),
        assets_builder=assets_builder,
        voice=req.voice,
        duration=req.duration,
        image_motion=req.image_motion,
        voice_lang="ko-KR",
        voice_voice="ko-KR-SunHiNeural",
        mode="render",
    )
    return {"ok": True, "jobId": job_id, **result}


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
    _job_update(output_dir, job_id, {"status": "queued", "mode": "render_upload"})

    uploads: list[tuple[str, bytes]] = []
    for idx, file in enumerate(media):
        name = Path(file.filename or f"file_{idx}").name
        uploads.append((f"{idx:04d}_{name}", await file.read()))

    def assets_builder(dst: Path):
        created: list[Path] = []
        for name, blob in uploads:
            out = dst / name
            out.write_bytes(blob)
            created.append(out)
        return created

    normalized_script = _normalize_script_text(script_text)
    script_max_end = _script_max_end_seconds(normalized_script)
    effective_duration = duration if duration >= script_max_end else script_max_end

    result = _run_pipeline(
        job_id=job_id,
        script_text=normalized_script,
        assets_builder=assets_builder,
        voice=voice,
        duration=effective_duration,
        image_motion=image_motion,
        voice_lang=voice_lang,
        voice_voice=voice_voice,
        mode="render_upload",
    )
    return {"ok": True, "jobId": job_id, **result, "message": "render completed"}


@app.post("/generate-creative")
def generate_creative(req: CreativeRequest):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic is empty")

    output_dir = _resolve_output_dir()
    job_id = uuid4().hex
    actual_mode = req.generation_mode
    warning: str | None = None
    if req.generation_mode == "external_video" and not _has_external_video_env():
        actual_mode = "mock"
        warning = "external_video 환경 변수가 없어 mock 모드로 대체되었습니다."
    if req.generation_mode == "replicate_video" and not _has_replicate_env():
        actual_mode = "mock"
        warning = "replicate_video 환경 변수가 없어 mock 모드로 대체되었습니다."

    _job_update(output_dir, job_id, {"status": "queued", "mode": actual_mode})
    scene_count = 6
    script_text = _build_script(topic=req.topic, tone=req.tone, duration=req.duration)

    def assets_builder(dst: Path):
        if actual_mode == "openai_image":
            return _generate_openai_image_assets(dst, req.topic, req.tone, req.style, scene_count)
        if actual_mode == "external_video":
            return _generate_external_video_assets(dst, req.topic, req.tone, req.style, scene_count)
        if actual_mode == "replicate_video":
            return _generate_replicate_video_assets(dst, req.topic, req.tone, req.style, scene_count)
        return _generate_mock_assets(_resolve_ffmpeg_bin(), dst, req.duration, scene_count)

    result = _run_pipeline(
        job_id=job_id,
        script_text=script_text,
        assets_builder=assets_builder,
        voice=req.voice,
        duration=req.duration,
        image_motion=req.image_motion,
        voice_lang="ko-KR",
        voice_voice="ko-KR-SunHiNeural",
        mode=actual_mode,
    )
    preview = script_text.splitlines()[:8]
    update_payload = {"script_preview": preview}
    if warning:
        update_payload["warning"] = warning
    _job_update(output_dir, job_id, update_payload)

    response_payload = {
        "ok": True,
        "jobId": job_id,
        **result,
        "mode": actual_mode,
        "mode_requested": req.generation_mode,
        "script_preview": preview,
        "message": "creative render completed",
    }
    if warning:
        response_payload["warning"] = warning
    return response_payload
