/**
 * deriveSubScores — 4개 신뢰도 sub-score 추출/합성
 * ==================================================
 *
 * 백엔드가 실제 값을 제공하면 그대로 사용.
 * 기존 기사(NULL)이면 종합 점수에서 결정론적 합성 값을 유도한다.
 *
 * 합성 공식:
 *   base = overall credibility
 *   tone = clamp(base + seed(url, 0))     — ±5 변동
 *   density = clamp(base + seed(url, 1))
 *   quotes = clamp(base + seed(url, 2))
 *   journalist = journalist 있으면 100, 없으면 base * 0.5
 */

export function deriveSubScores(article) {
  if (!article) return { tone: 0, density: 0, quotes: 0, journalist: 0 };

  // 실제 값이 하나라도 있으면 실제 값 우선
  const hasReal =
    article.rb01_tone != null ||
    article.rb02_density != null ||
    article.rb03_quotes != null ||
    article.rb04_journalist != null;

  if (hasReal) {
    return {
      tone: article.rb01_tone ?? 0,
      density: article.rb02_density ?? 0,
      quotes: article.rb03_quotes ?? 0,
      journalist: article.rb04_journalist ?? 0,
    };
  }

  // 폴백: 종합 점수에서 합성
  const base = Number(article.credibility ?? 0);
  const url = String(article.url ?? '');

  const seed = (offset) => {
    let h = offset;
    for (let i = 0; i < url.length; i++) {
      h = (h * 31 + url.charCodeAt(i)) & 0xffff;
    }
    return (h % 11) - 5; // -5 ~ +5
  };

  const clamp = (v) => Math.max(0, Math.min(100, v));

  return {
    tone: clamp(base + seed(0)),
    density: clamp(base + seed(1)),
    quotes: clamp(base + seed(2)),
    journalist: article.journalist ? 100 : clamp(base * 0.5),
  };
}
