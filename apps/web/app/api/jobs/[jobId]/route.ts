import { NextRequest, NextResponse } from "next/server";

export async function GET(_: NextRequest, { params }: { params: { jobId: string } }) {
  const workerUrl = process.env.WORKER_API_URL || "http://localhost:8000";
  const jobId = params.jobId;
  if (!jobId) {
    return NextResponse.json({ error: "jobId가 필요합니다." }, { status: 400 });
  }

  try {
    const response = await fetch(`${workerUrl}/jobs/${jobId}`, {
      method: "GET",
      cache: "no-store"
    });

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { error: "작업 상태 조회 실패", workerStatus: response.status, detail: text },
        { status: 502 }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      {
        error: "작업 연결 실패",
        detail: error instanceof Error ? error.message : "unknown"
      },
      { status: 502 }
    );
  }
}
