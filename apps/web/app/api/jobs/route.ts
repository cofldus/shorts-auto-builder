import { randomUUID } from "crypto";
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const script = String(form.get("script") || "").trim();
  const voice = String(form.get("voice") || "none").trim();
  const imageMotion = String(form.get("imageMotion") || "none").trim();
  const durationSec = Number(form.get("durationSec") || 30);
  const voiceLang = String(form.get("voiceLang") || "ko-KR").trim();
  const voiceVoice = String(form.get("voiceVoice") || "ko-KR-SunHiNeural").trim();
  const mediaFiles = form.getAll("media").filter((f) => f instanceof File) as File[];

  if (!script) {
    return NextResponse.json({ error: "script가 비어 있습니다." }, { status: 400 });
  }
  if (mediaFiles.length === 0) {
    return NextResponse.json({ error: "이미지 또는 영상을 최소 1개 첨부하세요." }, { status: 400 });
  }
  if (!["none", "edge", "openai", "piper"].includes(voice)) {
    return NextResponse.json({ error: "voice 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!["none", "slow"].includes(imageMotion)) {
    return NextResponse.json({ error: "imageMotion 값이 올바르지 않습니다." }, { status: 400 });
  }

  const workerUrl = process.env.WORKER_API_URL || "http://localhost:8000";
  const jobId = randomUUID();

  const workerForm = new FormData();
  workerForm.append("script_text", script);
  workerForm.append("voice", voice);
  workerForm.append("duration", String(durationSec));
  workerForm.append("image_motion", imageMotion);
  workerForm.append("voice_lang", voiceLang);
  workerForm.append("voice_voice", voiceVoice);
  for (const file of mediaFiles) {
    workerForm.append("media", file, file.name);
  }

  try {
    const response = await fetch(`${workerUrl}/render-upload`, {
      method: "POST",
      body: workerForm
    });

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { error: "워커 렌더링 요청 실패", workerStatus: response.status, detail: text },
        { status: 502 }
      );
    }

    const data = await response.json();
    return NextResponse.json({
      ok: true,
      jobId,
      workerUrl,
      statusCheckUrl: `/api/jobs/${data.jobId || jobId}`,
      uploadCount: mediaFiles.length,
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
