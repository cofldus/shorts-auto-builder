import "./globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";

export const metadata: Metadata = {
  title: "쇼츠 자동화 스튜디오",
  description: "키워드 기반 스크립트 생성 + 첨부 미디어 자동 편집"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
