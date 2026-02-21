#!/usr/bin/env bash
set -euo pipefail

# 브랜치별 PR 재생성을 돕는 보조 스크립트입니다.
# - 현재 체크아웃 가능한 로컬 브랜치 목록을 순회
# - 각 브랜치의 최신 커밋 기준으로 한국어 PR 제목/본문 템플릿 출력
# 실제 PR 생성은 저장소 정책/도구(gh, 웹 UI)에 맞춰 수동으로 진행하세요.

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "[오류] Git 저장소에서 실행해 주세요." >&2
  exit 1
fi

current_branch="$(git branch --show-current)"
mapfile -t branches < <(git for-each-ref --format='%(refname:short)' refs/heads)

if [[ ${#branches[@]} -eq 0 ]]; then
  echo "[안내] 로컬 브랜치가 없습니다."
  exit 0
fi

echo "[안내] 브랜치별 PR 재생성용 템플릿"
echo ""

for branch in "${branches[@]}"; do
  git checkout "$branch" >/dev/null 2>&1
  commit_subject="$(git log -1 --pretty=%s)"

  cat <<TEMPLATE
========================================
브랜치: $branch
권장 PR 제목: ${branch} 브랜치 변경사항 재작성

권장 PR 본문:
## 배경
- ${branch} 브랜치의 변경사항을 최신 기준으로 다시 공유하기 위해 PR을 재작성합니다.

## 변경 사항
- 최신 커밋: ${commit_subject}
- 세부 변경 내역은 커밋/파일 diff를 참고해 주세요.

## 테스트
- 브랜치에서 실행한 검증 명령과 결과를 여기에 기입해 주세요.
========================================

TEMPLATE
done

# 원래 브랜치 복귀
if [[ -n "$current_branch" ]]; then
  git checkout "$current_branch" >/dev/null 2>&1
fi

echo "[완료] 템플릿 출력을 마쳤습니다."
