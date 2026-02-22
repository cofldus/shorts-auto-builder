"use client";

import { FormEvent, useMemo, useState } from "react";

type JobResponse = {
  ok: boolean;
  jobId: string;
  workerUrl: string;
  statusCheckUrl?: string;
  uploadCount: number;
  output_path?: string;
  output_url?: string;
  message?: string;
};

type CreativeResponse = {
  ok: boolean;
  jobId: string;
  workerUrl: string;
  statusCheckUrl?: string;
  status?: string;
  output_path?: string;
  output_url?: string;
  mode?: string;
  mode_requested?: string;
  runway_mode?: string;
  asset_count?: number;
  error?: string;
  warning?: string;
  message?: string;
};

export default function HomePage() {
  const [topic, setTopic] = useState("직장인 위로 30초");
  const [tone, setTone] = useState("담백하고 따뜻한 톤");
  const [durationSec, setDurationSec] = useState(30);
  const [style, setStyle] = useState("cinematic vertical short, natural light, realistic texture");
  const [generationMode, setGenerationMode] = useState("mock");
  const [runwayMode, setRunwayMode] = useState("text_to_video");
  const [runwayRatio, setRunwayRatio] = useState("720:1280");
  const [runwayDuration, setRunwayDuration] = useState(10);
  const [runwaySeed, setRunwaySeed] = useState("");
  const [runwaySourceMedia, setRunwaySourceMedia] = useState<File | null>(null);

  const [voice, setVoice] = useState("edge");
  const [voiceLang, setVoiceLang] = useState("ko-KR");
  const [voiceVoice, setVoiceVoice] = useState("ko-KR-SunHiNeural");
  const [imageMotion, setImageMotion] = useState("none");
  const [script, setScript] = useState("");

  const [loadingScript, setLoadingScript] = useState(false);
  const [loadingJob, setLoadingJob] = useState(false);
  const [loadingCreative, setLoadingCreative] = useState(false);

  const [jobResult, setJobResult] = useState<JobResponse | null>(null);
  const [creativeResult, setCreativeResult] = useState<CreativeResponse | null>(null);
  const [error, setError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");

  const canCreateJob = useMemo(() => script.trim().length > 0, [script]);

  async function pollCreativeStatus(statusCheckUrl: string, jobId: string) {
    for (let i = 0; i < 240; i++) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      try {
        const res = await fetch(statusCheckUrl, { cache: "no-store" });
        if (!res.ok) continue;
        const job = await res.json();
        setCreativeResult((prev) => ({
          ok: prev?.ok ?? true,
          jobId,
          workerUrl: prev?.workerUrl ?? "",
          statusCheckUrl,
          status: job.status ?? prev?.status,
          output_path: job.output_path ?? prev?.output_path,
          output_url: job.output_url ?? prev?.output_url,
          mode: job.mode ?? prev?.mode,
          mode_requested: prev?.mode_requested,
          runway_mode: prev?.runway_mode,
          asset_count: job.asset_count ?? prev?.asset_count,
          warning: job.warning ?? prev?.warning,
          error: job.error ?? prev?.error,
          message:
            job.status === "completed"
              ? "creative render completed"
              : job.status === "failed"
                ? `실패: ${job.error ?? "unknown"}`
                : "작업 진행 중..."
        }));

        if (job.status === "completed") return;
        if (job.status === "failed") {
          setError(`생성 실패: ${job.error ?? "unknown"}`);
          return;
        }
      } catch {
        continue;
      }
    }
    setError("작업 상태 조회 시간이 초과되었습니다. 상태 조회 링크로 확인하세요.");
  }

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
      if (!res.ok) throw new Error(await res.text());
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
    form.set("voiceLang", voiceLang);
    form.set("voiceVoice", voiceVoice);
    form.set("imageMotion", imageMotion);
    form.set("durationSec", String(durationSec));

    try {
      const res = await fetch("/api/jobs", { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as JobResponse;
      setJobResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "작업 등록 실패");
    } finally {
      setLoadingJob(false);
    }
  }

  async function onCreateCreative() {
    setError("");
    setLoadingCreative(true);
    setCreativeResult(null);
    try {
      const form = new FormData();
      form.append("topic", topic);
      form.append("tone", tone);
      form.append("duration", String(durationSec));
      form.append("style", style);
      form.append("voice", voice);
      form.append("imageMotion", imageMotion);
      form.append("generationMode", generationMode);
      form.append("runwayMode", runwayMode);
      form.append("runwayRatio", runwayRatio);
      form.append("runwayDuration", String(runwayDuration));
      form.append("runwaySeed", runwaySeed.trim());
      if (runwaySourceMedia) {
        form.append("sourceMedia", runwaySourceMedia, runwaySourceMedia.name);
      }

      const res = await fetch("/api/creative", {
        method: "POST",
        body: form
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as CreativeResponse;
      setCreativeResult(data);
      if (data.statusCheckUrl && data.status !== "completed") {
        void pollCreativeStatus(data.statusCheckUrl, data.jobId);
      }
      if (!script.trim()) await onGenerateScript();
    } catch (e) {
      setError(e instanceof Error ? e.message : "생성형 작업 등록 실패");
    } finally {
      setLoadingCreative(false);
    }
  }

  async function onCopyOutputUrl(url?: string) {
    if (!url) {
      setCopyMessage("복사할 URL이 없습니다.");
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopyMessage("출력 URL을 복사했습니다.");
    } catch {
      setCopyMessage("복사에 실패했습니다. 브라우저 권한을 확인하세요.");
    }
  }

  return (
    <main>
      <h1>쇼츠 자동화 스튜디오</h1>
      <p>첨부 편집과 생성형 영상을 한 화면에서 처리합니다.</p>

      <div className="grid">
        <section className="card">
          <h2>스크립트 자동 생성</h2>
          <label htmlFor="topic">주제 키워드</label>
          <input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} />

          <label htmlFor="tone">톤</label>
          <input id="tone" value={tone} onChange={(e) => setTone(e.target.value)} />

          <label htmlFor="duration">길이(초)</label>
          <input id="duration" type="number" min={10} max={120} value={durationSec} onChange={(e) => setDurationSec(Number(e.target.value) || 30)} />

          <button type="button" disabled={loadingScript} onClick={onGenerateScript}>
            {loadingScript ? "생성 중..." : "스크립트 생성"}
          </button>

          <label htmlFor="script">생성된 script.txt</label>
          <textarea id="script" value={script} onChange={(e) => setScript(e.target.value)} />
        </section>

        <section className="card">
          <h2>첨부 편집 모드</h2>
          <form onSubmit={onCreateJob}>
            <label htmlFor="voice">음성 모드</label>
            <select id="voice" name="voice" value={voice} onChange={(e) => setVoice(e.target.value)}>
              <option value="none">none (무음/배경음만)</option>
              <option value="edge">edge (무료)</option>
              <option value="piper">piper (로컬 무료)</option>
              <option value="openai">openai (유료)</option>
            </select>

            <label htmlFor="voiceLang">음성 언어</label>
            <input id="voiceLang" name="voiceLang" value={voiceLang} onChange={(e) => setVoiceLang(e.target.value)} />

            <label htmlFor="voiceVoice">음성 화자</label>
            <input id="voiceVoice" name="voiceVoice" value={voiceVoice} onChange={(e) => setVoiceVoice(e.target.value)} />

            <label htmlFor="imageMotion">이미지 모션</label>
            <select id="imageMotion" name="imageMotion" value={imageMotion} onChange={(e) => setImageMotion(e.target.value)}>
              <option value="none">none (정지)</option>
              <option value="slow">slow (완만한 줌)</option>
            </select>

            <label htmlFor="media">첨부 이미지/영상</label>
            <input id="media" name="media" type="file" multiple accept="image/*,video/*" />

            <button type="submit" disabled={!canCreateJob || loadingJob}>
              {loadingJob ? "등록 중..." : "첨부 편집 실행"}
            </button>
          </form>

          {jobResult ? (
            <p className="result">
              작업 ID: {jobResult.jobId}
              <br />출력 경로: {jobResult.output_path || "(워커 응답 대기)"}
              <br />출력 URL: {jobResult.output_url || "(미설정)"}
              {jobResult.output_url ? (
                <>
                  <br />
                  <span className="result-actions">
                    <a className="result-link" href={jobResult.output_url} target="_blank" rel="noreferrer">
                      링크 열기
                    </a>
                    <button type="button" className="copy-button" onClick={() => onCopyOutputUrl(jobResult.output_url)}>
                      URL 복사
                    </button>
                  </span>
                </>
              ) : null}
              <br />상태 조회: {jobResult.statusCheckUrl || "(미설정)"}
              <br />메시지: {jobResult.message || "등록 완료"}
            </p>
          ) : null}
        </section>

        <section className="card card-wide">
          <h2>생성형 영상 모드</h2>
          <label htmlFor="style">비주얼 스타일 프롬프트</label>
          <textarea id="style" value={style} onChange={(e) => setStyle(e.target.value)} />

          <label htmlFor="generationMode">생성 방식</label>
          <select id="generationMode" value={generationMode} onChange={(e) => setGenerationMode(e.target.value)}>
            <option value="mock">mock (로컬 생성, 비용 없음)</option>
            <option value="openai_image">openai_image (이미지 생성 API)</option>
            <option value="external_video">external_video (외부 영상 생성 API)</option>
            <option value="replicate_video">replicate_video (Replicate 전용)</option>
            <option value="runway">runway (Text/Image/Video to Video)</option>
          </select>

          {generationMode === "runway" ? (
            <>
              <label htmlFor="runwayMode">Runway 모드</label>
              <select id="runwayMode" value={runwayMode} onChange={(e) => setRunwayMode(e.target.value)}>
                <option value="text_to_video">text_to_video</option>
                <option value="image_to_video">image_to_video</option>
                <option value="video_to_video">video_to_video</option>
              </select>

              <label htmlFor="runwayRatio">Runway 비율</label>
              <input id="runwayRatio" value={runwayRatio} onChange={(e) => setRunwayRatio(e.target.value)} />

              <label htmlFor="runwayDuration">Runway 클립 길이(2~10초)</label>
              <input
                id="runwayDuration"
                type="number"
                min={2}
                max={10}
                value={runwayDuration}
                onChange={(e) => setRunwayDuration(Number(e.target.value) || 10)}
              />

              <label htmlFor="runwaySeed">Runway 시드(선택)</label>
              <input id="runwaySeed" value={runwaySeed} onChange={(e) => setRunwaySeed(e.target.value)} />

              <label htmlFor="runwaySourceMedia">
                소스 파일(이미지/비디오 모드 필수)
              </label>
              <input
                id="runwaySourceMedia"
                type="file"
                accept="image/*,video/*"
                onChange={(e) => setRunwaySourceMedia(e.target.files?.[0] || null)}
              />
            </>
          ) : null}

          <button type="button" disabled={loadingCreative} onClick={onCreateCreative}>
            {loadingCreative ? "생성 중..." : "무에서 유 생성 실행"}
          </button>

          {creativeResult ? (
            <p className="result">
              작업 ID: {creativeResult.jobId}
              <br />출력 경로: {creativeResult.output_path || "(워커 응답 대기)"}
              <br />출력 URL: {creativeResult.output_url || "(미설정)"}
              {creativeResult.output_url ? (
                <>
                  <br />
                  <span className="result-actions">
                    <a className="result-link" href={creativeResult.output_url} target="_blank" rel="noreferrer">
                      링크 열기
                    </a>
                    <button type="button" className="copy-button" onClick={() => onCopyOutputUrl(creativeResult.output_url)}>
                      URL 복사
                    </button>
                  </span>
                </>
              ) : null}
              <br />상태 조회: {creativeResult.statusCheckUrl || "(미설정)"}
              <br />상태: {creativeResult.status || "-"}
              <br />모드: {creativeResult.mode || "-"} (요청: {creativeResult.mode_requested || "-"})
              <br />Runway 모드: {creativeResult.runway_mode || "-"}
              <br />생성 자산 수: {creativeResult.asset_count ?? "-"}
              <br />오류: {creativeResult.error || "-"}
              <br />주의: {creativeResult.warning || "-"}
              <br />메시지: {creativeResult.message || "등록 완료"}
            </p>
          ) : null}
        </section>
      </div>

      {copyMessage ? <p className="result">{copyMessage}</p> : null}
      {error ? <p className="result">오류: {error}</p> : null}
    </main>
  );
}
