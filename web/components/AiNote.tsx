// AI 작성 안내 — 결정 56(사이트 공개). 카드·브리핑은 사람이 검토하지 않은 AI 글이라는 것을 읽는 사람에게 밝힌다
const TEXT = {
  card: "이 카드는 AI(Claude)가 공개 자료(README·릴리스·HN·웹 글)로 쓴 요약입니다. 사람이 검토하지 않았으며, 주장마다 출처 링크와 확인·추정 표시를 붙였습니다. 숫자는 GitHub API 값을 코드가 채웁니다.",
  briefing: "이 브리핑은 AI(Claude)가 랭킹과 카드를 바탕으로 쓴 요약입니다. 사람이 검토하지 않았으며, 주장마다 출처 링크를 붙였습니다. 숫자는 GitHub API 값을 코드가 채웁니다.",
} as const;

export function AiNote({ kind }: { kind: keyof typeof TEXT }) {
  return (
    <p className="ai-note" role="note">
      <span className="ai-badge">AI 작성</span>
      {TEXT[kind]}
    </p>
  );
}
