import { randomUUID } from "crypto";
import { NextRequest, NextResponse } from "next/server";

const ALLOWED_VOICE = new Set(["none", "edge", "openai", "piper"]);
const ALLOWED_IMAGE_MOTION = new Set(["none", "slow"]);
const ALLOWED_GENERATION_MODE = new Set(["mock", "openai_image", "external_video", "replicate_video", "runway"]);
const ALLOWED_RUNWAY_MODE = new Set(["text_to_video", "image_to_video", "video_to_video"]);

type CreativeParams = {
  topic: string;
  tone: string;
  style: string;
  duration: number;
  voice: string;
  imageMotion: string;
  generationMode: string;
  runwayMode: string;
  runwayRatio: string;
  runwayDuration: number;
  runwaySeed: string;
  sourceMedia?: File;
};

function parseNumeric(value: FormDataEntryValue | string | null | undefined, fallback: number): number {
  const n = Number(value ?? fallback);
  return Number.isFinite(n) ? n : fallback;
}

function validateParams(params: CreativeParams): NextResponse | null {
  if (!params.topic) {
    return NextResponse.json({ error: "topic이 비어 있습니다." }, { status: 400 });
  }
  if (!Number.isFinite(params.duration) || params.duration <= 0 || params.duration > 120) {
    return NextResponse.json({ error: "duration 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!ALLOWED_VOICE.has(params.voice)) {
    return NextResponse.json({ error: "voice 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!ALLOWED_IMAGE_MOTION.has(params.imageMotion)) {
    return NextResponse.json({ error: "imageMotion 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!ALLOWED_GENERATION_MODE.has(params.generationMode)) {
    return NextResponse.json({ error: "generationMode 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!ALLOWED_RUNWAY_MODE.has(params.runwayMode)) {
    return NextResponse.json({ error: "runwayMode 값이 올바르지 않습니다." }, { status: 400 });
  }
  if (!Number.isFinite(params.runwayDuration) || params.runwayDuration < 2 || params.runwayDuration > 10) {
    return NextResponse.json({ error: "runwayDuration 값은 2~10이어야 합니다." }, { status: 400 });
  }
  if (params.generationMode === "runway" && (params.runwayMode === "image_to_video" || params.runwayMode === "video_to_video") && !params.sourceMedia) {
    return NextResponse.json({ error: "runway image/video 모드에는 sourceMedia 파일이 필요합니다." }, { status: 400 });
  }
  return null;
}

async function parseRequest(req: NextRequest): Promise<CreativeParams> {
  const contentType = req.headers.get("content-type") || "";
  if (contentType.includes("multipart/form-data")) {
    const form = await req.formData();
    const sourceCandidate = form.get("sourceMedia");
    const sourceMedia = sourceCandidate instanceof File && sourceCandidate.size > 0 ? sourceCandidate : undefined;
    return {
      topic: String(form.get("topic") || "").trim(),
      tone: String(form.get("tone") || "Calm and immersive").trim(),
      style: String(form.get("style") || "cinematic vertical short").trim(),
      duration: parseNumeric(form.get("duration"), 30),
      voice: String(form.get("voice") || "edge").trim(),
      imageMotion: String(form.get("imageMotion") || "slow").trim(),
      generationMode: String(form.get("generationMode") || "mock").trim(),
      runwayMode: String(form.get("runwayMode") || "text_to_video").trim(),
      runwayRatio: String(form.get("runwayRatio") || "720:1280").trim(),
      runwayDuration: parseNumeric(form.get("runwayDuration"), 10),
      runwaySeed: String(form.get("runwaySeed") || "").trim(),
      sourceMedia
    };
  }

  const body = await req.json();
  return {
    topic: String(body.topic || "").trim(),
    tone: String(body.tone || "Calm and immersive").trim(),
    style: String(body.style || "cinematic vertical short").trim(),
    duration: parseNumeric(body.duration, 30),
    voice: String(body.voice || "edge").trim(),
    imageMotion: String(body.imageMotion || "slow").trim(),
    generationMode: String(body.generationMode || "mock").trim(),
    runwayMode: String(body.runwayMode || "text_to_video").trim(),
    runwayRatio: String(body.runwayRatio || "720:1280").trim(),
    runwayDuration: parseNumeric(body.runwayDuration, 10),
    runwaySeed: String(body.runwaySeed || "").trim()
  };
}

export async function POST(req: NextRequest) {
  const params = await parseRequest(req);
  const validationError = validateParams(params);
  if (validationError) return validationError;

  const workerUrl = process.env.WORKER_API_URL || "http://localhost:8000";
  const jobId = randomUUID();
  const shouldUseUploadEndpoint = params.generationMode === "runway" || Boolean(params.sourceMedia);

  try {
    const response = shouldUseUploadEndpoint
      ? await (async () => {
          const workerForm = new FormData();
          workerForm.append("topic", params.topic);
          workerForm.append("tone", params.tone);
          workerForm.append("duration", String(params.duration));
          workerForm.append("style", params.style);
          workerForm.append("voice", params.voice);
          workerForm.append("image_motion", params.imageMotion);
          workerForm.append("generation_mode", params.generationMode);
          workerForm.append("runway_mode", params.runwayMode);
          workerForm.append("runway_ratio", params.runwayRatio);
          workerForm.append("runway_duration", String(params.runwayDuration));
          workerForm.append("runway_seed", params.runwaySeed);
          if (params.sourceMedia) {
            workerForm.append("source_media", params.sourceMedia, params.sourceMedia.name);
          }
          return fetch(`${workerUrl}/generate-creative-upload-async`, {
            method: "POST",
            body: workerForm
          });
        })()
      : await fetch(`${workerUrl}/generate-creative-async`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            topic: params.topic,
            tone: params.tone,
            style: params.style,
            duration: params.duration,
            voice: params.voice,
            image_motion: params.imageMotion,
            generation_mode: params.generationMode,
            runway_mode: params.runwayMode,
            runway_ratio: params.runwayRatio,
            runway_duration: params.runwayDuration,
            runway_seed: params.runwaySeed ? Number(params.runwaySeed) : undefined
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
      statusCheckUrl: `/api/jobs/${data.jobId || jobId}`,
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
