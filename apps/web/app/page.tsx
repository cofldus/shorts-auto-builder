"use client";

import { FormEvent, useMemo, useState } from "react";

type JobResponse = {
  ok: boolean;
  jobId: string;
  workerUrl: string;
  uploadCount: number;
  message: string;
};

export default function HomePage() {
  const [topic, setTopic] = useState("직장인 위로 30초");
  const [tone, setTone] = useState("담백하고 따뜻한 톤");
  const [durationSec, setDurationSec] = useState(30);
  const [voice, setVoice] = useState("edge");
  const [script, setScript] = useState("");
  const [loadingScript, setLoadingScript] = useState(false);
  const [loadingJob, setLoadingJob] = useState(false);
  const [jobResult, setJobResult] = useState<JobResponse | null>(null);
  const [error, setError] = useState("");

  const canCreateJob = useMemo(() => script.trim().length > 0, [script]);

  async function onGenerateScript() {
    setError("");
    setLoadingScript(true);
    setJobResult(null);
    try {
      const res = await fetch("/api/script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, tone, durationSec })
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = await res.json();
      setScript(data.script);
    } catch (e) {
      setError(e instanceof Error ? e.message : "스크립트 생성 실패");
    } finally {
      setLoadingScript(false);
    }
  }

  async function onCreateJob(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoadingJob(true);
    setJobResult(null);
    const form = new FormData(e.currentTarget);
    form.set("script", script);
    form.set("voice", voice);
    form.set("durationSec", String(durationSec));

    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        body: form
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = (await res.json()) as JobResponse;
      setJobResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "작업 등록 실패");
    } finally {
      setLoadingJob(false);
    }
  }

  return (
    <main>
      <h1>쇼츠 자동화 스튜디오</h1>
      <p>주제 키워드로 스크립트를 만들고, 첨부 미디어 기반 편집 작업을 등록합니다.</p>

      <div className="grid">
        <section className="card">
          <h2>스크립트 자동 생성</h2>
          <label htmlFor="topic">주제 키워드</label>
          <input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} />

          <label htmlFor="tone">톤</label>
          <input id="tone" value={tone} onChange={(e) => setTone(e.target.value)} />

          <label htmlFor="duration">길이(초)</label>
          <input
            id="duration"
            type="number"
            min={10}
            max={90}
            value={durationSec}
            onChange={(e) => setDurationSec(Number(e.target.value) || 30)}
          />

          <button type="button" disabled={loadingScript} onClick={onGenerateScript}>
            {loadingScript ? "생성 중..." : "스크립트 생성"}
          </button>

          <label htmlFor="script">생성된 script.txt</label>
          <textarea id="script" value={script} onChange={(e) => setScript(e.target.value)} />
        </section>

        <section className="card">
          <h2>미디어 편집 작업 등록</h2>
          <form onSubmit={onCreateJob}>
            <label htmlFor="voice">음성 모드</label>
            <select id="voice" name="voice" value={voice} onChange={(e) => setVoice(e.target.value)}>
              <option value="none">none (무음/배경음만)</option>
              <option value="edge">edge (무료)</option>
              <option value="openai">openai (유료)</option>
            </select>

            <label htmlFor="media">첨부 이미지/영상</label>
            <input id="media" name="media" type="file" multiple accept="image/*,video/*" />

            <button type="submit" disabled={!canCreateJob || loadingJob}>
              {loadingJob ? "등록 중..." : "작업 등록"}
            </button>
          </form>

          {jobResult ? (
            <p className="result">
              작업 ID: {jobResult.jobId}
              <br />
              워커 URL: {jobResult.workerUrl}
              <br />
              메시지: {jobResult.message}
            </p>
          ) : null}

          {error ? <p className="result">오류: {error}</p> : null}
        </section>
      </div>
    </main>
  );
}
