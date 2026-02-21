from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="shorts-render-worker")


class RenderRequest(BaseModel):
    script_path: str
    assets_path: str
    output_path: str = "output_from_worker.mp4"
    voice: str = Field(default="none", pattern="^(none|edge|openai)$")
    duration: float = 30.0
    image_motion: str = Field(default="none", pattern="^(none|slow)$")


@app.post("/render")
def render_video(req: RenderRequest):
    script = Path(req.script_path)
    assets = Path(req.assets_path)

    if not script.exists():
        raise HTTPException(status_code=400, detail=f"script_path not found: {script}")
    if not assets.exists() or not assets.is_dir():
        raise HTTPException(status_code=400, detail=f"assets_path not found: {assets}")

    cmd = [
        "python",
        "-m",
        "shorts_maker",
        "--script",
        str(script),
        "--assets",
        str(assets),
        "--out",
        req.output_path,
        "--voice",
        req.voice,
        "--duration",
        str(req.duration),
        "--image-motion",
        req.image_motion,
    ]

    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={"stderr": completed.stderr[-4000:], "stdout": completed.stdout[-4000:]},
        )

    return {
        "ok": True,
        "output_path": req.output_path,
        "stdout": completed.stdout[-2000:],
    }
