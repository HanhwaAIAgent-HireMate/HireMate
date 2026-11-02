import type { PostingContent } from '@/features/posting/api'

/** 고용 형태는 이 넷 중에서만 고른다. backend PostingContentRequest, ai reviser와 같다 */
export const EMPLOYMENT_TYPES = ['정규직', '계약직', '인턴', '파견직'] as const

/** 경력 종류. 경력은 "경력 N년 이상"으로 연차를 붙일 수 있다. backend PostingContentRequest, ai reviser와 같다 */
export const CAREER_KINDS = ['신입', '경력', '경력 무관'] as const
export type CareerKind = (typeof CAREER_KINDS)[number]
export const MAX_CAREER_YEARS = 99

/** 저장된 경력 글을 종류와 연차로 나눈다. 넷 중 어느 모양도 아니면(예전에 글로 적은 값) 종류는 null이다 */
export function parseCareer(career: string): { kind: CareerKind | null; years: number | null } {
  const years = /^경력 (\d+)년 이상$/.exec(career)
  if (years) return { kind: '경력', years: Number(years[1]) }
  const kind = CAREER_KINDS.find((item) => item === career)
  return { kind: kind ?? null, years: null }
}

/** 종류와 연차로 저장할 경력 글을 만든다. 연차는 경력일 때만 붙고, 비우면 "경력"이다 */
export function formatCareer(kind: CareerKind, years: number | null): string {
  return kind === '경력' && years ? `경력 ${years}년 이상` : kind
}

/** 연차 칸 글을 1~MAX_CAREER_YEARS 숫자로 바꾼다. 비우거나 범위 밖이면 null이다 */
export function toCareerYears(value: string): number | null {
  const years = Number(value)
  return value !== '' && Number.isInteger(years) && years >= 1 && years <= MAX_CAREER_YEARS
    ? years
    : null
}

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
    label: '근무 요일 · 시간',
    placeholder: '예: 주 5일(월~금) 10:00~19:00',
    maxLength: 100,
    wide: true,
  },
]

export const MAX_HEADCOUNT = 9999

export type WorkKey = 'location' | 'workHours' | 'salary'

/** 근무 조건 묶음: 어디서 · 언제 · 얼마에 일하나. 길이는 backend job_postings 테이블과 같다 */
export const WORK_FIELDS: {
  key: WorkKey
  label: string
  placeholder: string
  maxLength: number
}[] = [
  { key: 'location', label: '근무지', placeholder: '예: 서울 강남구 테헤란로 123', maxLength: 100 },
  ...(['workHours', 'salary'] as const).flatMap((key) =>
    CONDITION_FIELDS.filter((field) => field.key === key).map((field) => ({ ...field, key })),
  ),
]

/** 수정안을 한 덩어리로 처리하는 근무 조건 칸 */
export const WORK_KEYS: string[] = WORK_FIELDS.map((field) => field.key)

/** 지원자 화면의 근무 조건. 비어 있는 칸은 뺀다 */
export function workRows(content: PostingContent): { label: string; value: string }[] {
  return WORK_FIELDS.map((field) => ({ label: field.label, value: content[field.key] })).filter(
    (row) => row.value,
  )
}

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
