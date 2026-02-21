import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { buildScriptPrompt } from "@/lib/prompt";

const schema = z.object({
  topic: z.string().min(2),
  tone: z.string().min(2),
  durationSec: z.number().min(10).max(90)
});

function fallbackScript(topic: string, durationSec: number): string {
  const third = Math.floor(durationSec / 3);
  const second = third * 2;
  return [
    "start: 0.0",
    `end: ${third}.0`,
    `subtitle: ${topic}의 시작`,
    `narration: 오늘의 주제는 ${topic}입니다.`,
    "",
    `start: ${third}.0`,
    `end: ${second}.0`,
    "subtitle: 핵심 포인트",    
    "narration: 가장 중요한 핵심 한 가지에 집중해봅시다.",
    "",
    `start: ${second}.0`,
    `end: ${durationSec}.0`,
    "subtitle: 마무리",    
    "narration: 지금 바로 짧게 실천해보면 변화가 시작됩니다."
  ].join("\n");
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const parsed = schema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json({ error: "입력값이 올바르지 않습니다." }, { status: 400 });
    }

    const { topic, tone, durationSec } = parsed.data;
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      return NextResponse.json({ script: fallbackScript(topic, durationSec), source: "fallback" });
    }

    const model = process.env.OPENAI_SCRIPT_MODEL || "gpt-4o-mini";
    const prompt = buildScriptPrompt(topic, tone, durationSec);

    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model,
        input: prompt
      })
    });

    if (!response.ok) {
      return NextResponse.json({ script: fallbackScript(topic, durationSec), source: "fallback" });
    }

    const data = await response.json();
    const script = data.output_text?.trim();
    if (!script) {
      return NextResponse.json({ script: fallbackScript(topic, durationSec), source: "fallback" });
    }

    return NextResponse.json({ script, source: "openai" });
  } catch {
    return NextResponse.json({ error: "스크립트 생성 중 오류가 발생했습니다." }, { status: 500 });
  }
}
