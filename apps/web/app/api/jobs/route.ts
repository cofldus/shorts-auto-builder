import { randomUUID } from "crypto";
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const script = String(form.get("script") || "").trim();
  const voice = String(form.get("voice") || "none").trim();
  const durationSec = Number(form.get("durationSec") || 30);
  const mediaFiles = form.getAll("media").filter((f) => f instanceof File) as File[];

  if (!script) {
    return NextResponse.json({ error: "script가 비어 있습니다." }, { status: 400 });
  }

  if (mediaFiles.length === 0) {
    return NextResponse.json({ error: "이미지 또는 영상을 최소 1개 첨부하세요." }, { status: 400 });
  }

  const workerUrl = process.env.WORKER_API_URL || "http://localhost:8000";
  const jobId = randomUUID();

  return NextResponse.json({
    ok: true,
    jobId,
    workerUrl,
    uploadCount: mediaFiles.length,
    message:
      "작업이 등록되었습니다. 다음 단계로 워커 API에서 파일 업로드 URL 발급 -> 렌더링 실행 -> 결과 URL 반환을 구현하세요.",
    payloadPreview: {
      voice,
      durationSec,
      scriptFirstLine: script.split("\n")[0]
    }
  });
}
