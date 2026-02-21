from __future__ import annotations

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
