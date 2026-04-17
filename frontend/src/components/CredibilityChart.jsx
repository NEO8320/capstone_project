/**
 * CredibilityChart — 4-지표 신뢰도 분석 차트
 * =============================================
 *
 * 표시 항목:
 *   - 종합 점수 (숫자) + 등급 뱃지 (높음/보통/낮음)
 *   - 4개 지표 progress bar:
 *     1. 문체 중립성 (RB-01)
 *     2. 정보 밀도 (RB-02)
 *     3. 인용구 존재 (RB-03)
 *     4. 기자 실명 (RB-04)
 *
 * 데이터 소스:
 *   - 백엔드에서 실제 값 제공 시 그대로 사용
 *   - NULL이면 deriveSubScores()로 종합 점수에서 합성
 */

import { deriveSubScores } from '../utils/credibility';
import './CredibilityChart.css';

const METRICS = [
  { key: 'tone', label: '문체 중립성', weight: '30%' },
  { key: 'density', label: '정보 밀도', weight: '25%' },
  { key: 'quotes', label: '인용구 존재 여부', weight: '25%' },
  { key: 'journalist', label: '기자 실명', weight: '20%' },
];

function gradeBadge(score) {
  if (score >= 90) return { label: '높음', variant: 'green' };
  if (score >= 70) return { label: '보통', variant: 'yellow' };
  return { label: '낮음', variant: 'red' };
}

export default function CredibilityChart({ article }) {
  const overall = Number(article?.credibility ?? 0);
  const subs = deriveSubScores(article);
  const grade = gradeBadge(overall);

  return (
    <section className="cred-chart">
      <header className="cred-chart__header">
        <h3 className="cred-chart__title">신뢰도 분석</h3>
        <div className="cred-chart__overall">
          <span className={`cred-chart__score cred-chart__score--${grade.variant}`}>
            {Math.round(overall)}
          </span>
          <span className={`cred-chart__badge cred-chart__badge--${grade.variant}`}>
            {grade.label}
          </span>
        </div>
      </header>

      <ul className="cred-chart__metrics">
        {METRICS.map((m) => {
          const value = Math.max(0, Math.min(100, subs[m.key] ?? 0));
          return (
            <li key={m.key} className="cred-chart__row">
              <div className="cred-chart__row-header">
                <span className="cred-chart__label">{m.label}</span>
                <span className="cred-chart__weight">({m.weight})</span>
              </div>
              <div className="cred-chart__bar">
                <div
                  className="cred-chart__bar-fill"
                  style={{ width: `${value}%` }}
                />
              </div>
              <span className="cred-chart__value">{Math.round(value)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
