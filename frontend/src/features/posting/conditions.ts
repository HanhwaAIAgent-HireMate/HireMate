import type { PostingContent } from '@/features/posting/api'

/** 고용 형태는 이 넷 중에서만 고른다. backend PostingContentRequest, ai reviser와 같다 */
export const EMPLOYMENT_TYPES = ['정규직', '계약직', '인턴', '파견직'] as const

export type ConditionKey = 'headcount' | 'position' | 'education' | 'workHours' | 'salary'

/** 모집 조건 칸. 길이는 backend job_postings 테이블과 같다. 채용 인원은 숫자만 받는다 */
export const CONDITION_FIELDS: {
  key: ConditionKey
  label: string
  placeholder: string
  maxLength: number
  wide?: boolean
}[] = [
  { key: 'headcount', label: '채용 인원', placeholder: '예: 3', maxLength: 4 },
  { key: 'position', label: '직급', placeholder: '예: 사원~대리', maxLength: 50 },
  { key: 'education', label: '학력', placeholder: '예: 학력 무관, 대졸 이상', maxLength: 50 },
  { key: 'salary', label: '급여', placeholder: '예: 회사 내규에 따름', maxLength: 100 },
  {
    key: 'workHours',
    label: '근무 일시',
    placeholder: '예: 주 5일(월~금) 10:00~19:00',
    maxLength: 100,
    wide: true,
  },
]

export const MAX_HEADCOUNT = 9999

/** 수정안을 한 덩어리로 처리하는 모집 조건 칸 */
export const CONDITION_KEYS: string[] = CONDITION_FIELDS.map((field) => field.key)

/** 채용 인원 입력값. 1~9999의 정수만 받고 나머지는 비운다 */
export function toHeadcount(value: string): number | null {
  const count = Number(value)
  return value.trim() && Number.isInteger(count) && count >= 1 && count <= MAX_HEADCOUNT
    ? count
    : null
}

/** 지원자 화면에 보여 줄 모집 조건. 비어 있는 칸은 뺀다 */
export function conditionRows(content: PostingContent): { label: string; value: string }[] {
  return CONDITION_FIELDS.map((field) => ({
    label: field.label,
    value:
      field.key === 'headcount'
        ? content.headcount
          ? `${content.headcount}명`
          : ''
        : content[field.key],
  })).filter((row) => row.value)
}
