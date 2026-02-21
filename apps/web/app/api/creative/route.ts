import { randomUUID } from "crypto";
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const topic = String(body.topic || "").trim();
  const tone = String(body.tone || "담백하고 몰입감 있는 톤").trim();
  const style = String(body.style || "cinematic vertical short").trim();
  const duration = Number(body.duration || 30);
  const voice = String(body.voice || "edge").trim();
  const imageMotion = String(body.imageMotion || "slow").trim();
  const generationMode = String(body.generationMode || "mock").trim();

  if (!topic) {
    return NextResponse.json({ error: "topic이 비어 있습니다." }, { status: 400 });
  }
  if (!Number.isFinite(duration) || duration <= 0 || duration > 120) {
    return NextResponse.json({ error: "duration 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!["none", "edge", "openai", "piper"].includes(voice)) {
    return NextResponse.json({ error: "voice 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!["none", "slow"].includes(imageMotion)) {
    return NextResponse.json({ error: "imageMotion 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!["mock", "openai_image"].includes(generationMode)) {
    return NextResponse.json({ error: "generationMode 값이 올바르지 않습니다." }, { status: 400 });
  }

  const workerUrl = process.env.WORKER_API_URL || "http://localhost:8000";
  const jobId = randomUUID();

  try {
    const response = await fetch(`${workerUrl}/generate-creative`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic,
        tone,
        style,
        duration,
        voice,
        image_motion: imageMotion,
        generation_mode: generationMode
      })
    });

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { error: "생성형 워커 요청 실패", workerStatus: response.status, detail: text },
        { status: 502 }
      );
    }

    const data = await response.json();
    return NextResponse.json({
      ok: true,
      jobId,
      workerUrl,
      ...data
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "워커 연결 실패",
        detail: error instanceof Error ? error.message : "unknown"
      },
      { status: 502 }
    );
  }
}
