import type { ProfileItemView } from '@/features/screening/api'

export type Verification = ProfileItemView['verification']
export type VerificationFilter = Verification | 'ALL'

/** 확인 상태 이름과 칩 순서: 확인됨 → 근거 있음 → 미확인 → 상충 */
export const VERIFICATIONS: { key: Verification; label: string }[] = [
  { key: 'CONFIRMED', label: '확인됨' },
  { key: 'EVIDENCED', label: '근거 있음' },
  { key: 'UNCONFIRMED', label: '미확인' },
  { key: 'CONFLICT', label: '상충' },
]

/** 프로필 항목 분류 이름 (ai db.profile.ItemCategory) */
const CATEGORY_LABELS: Record<string, string> = {
  QUALIFICATION: '자격 조건',
  DOMAIN: '도메인',
  EXPERIENCE: '직무 경험',
  SKILL: '역량',
  COMPANY_FIT: '기업 관련',
  STRENGTH: '강점',
  CHECK: '확인 필요',
}

/** 항목을 만든 분석 단계 (ai db.profile.ItemAgent) */
const AGENT_LABELS: Record<string, string> = {
  application: '지원서 분석',
  assessment: '평가 분석',
  interview: '면접 분석',
}

export function verificationLabel(verification: Verification) {
  return VERIFICATIONS.find((item) => item.key === verification)?.label ?? verification
}

/** 모르는 분류(나중에 더해진 것)는 값을 그대로 보여 준다 */
export function categoryLabel(category: string) {
  return CATEGORY_LABELS[category] ?? category
}

export function agentLabel(agent: string) {
  return AGENT_LABELS[agent] ?? agent
}

/** 확인 상태별 항목 수. 칩 옆 숫자로 보여 준다 */
export function countByVerification(
  items: Pick<ProfileItemView, 'verification'>[],
): Record<VerificationFilter, number> {
  const counts = { ALL: items.length, CONFIRMED: 0, EVIDENCED: 0, UNCONFIRMED: 0, CONFLICT: 0 }
  for (const item of items) counts[item.verification] += 1
  return counts
}

/** 고른 확인 상태의 항목만 남긴다. 전체(ALL)면 그대로 */
export function filterByVerification<T extends Pick<ProfileItemView, 'verification'>>(
  items: T[],
  filter: VerificationFilter,
): T[] {
  return filter === 'ALL' ? items : items.filter((item) => item.verification === filter)
}
