export function buildScriptPrompt(topic: string, tone: string, durationSec: number): string {
  return [
    "너는 한국어 쇼츠 스크립트 작가다.",
    `주제: ${topic}`,
    `톤: ${tone}`,
    `총 길이: ${durationSec}초`,
    "반드시 아래 규칙을 지켜 script.txt 형식만 출력해라.",
    "- 구간은 빈 줄로 분리",
    "- 각 구간은 start, end, subtitle, narration 포함",
    "- start/end는 초 단위 소수 가능",
    "- 첫 구간은 0.0 시작",
    "- 마지막 end는 총 길이와 일치",
    "- 과장된 감탄사 남발 금지, 자연스러운 문장",
    "- 출력은 설명 없이 script 본문만"
  ].join("\n");
}
