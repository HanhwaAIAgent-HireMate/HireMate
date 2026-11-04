import createClient, { type Middleware } from 'openapi-fetch'

import type { components, paths } from './schema'

// 같은 출처의 /api로 요청한다. 개발 중에는 Vite 프록시가, 배포 후에는 Nginx가 Spring으로 넘긴다.
// 타입(schema.d.ts)은 backend를 띄운 뒤 `npm run api:generate`로 다시 만든다.
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? '',
  // 호출할 때의 fetch를 쓴다 (테스트에서 바꿔 끼울 수 있게)
  fetch: (request) => globalThis.fetch(request),
})

export type Schemas = components['schemas']

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
let csrf: Promise<{ token: string; headerName: string }> | null = null

async function fetchCsrf() {
  const response = await fetch('/api/auth/csrf', { credentials: 'same-origin' })
  if (!response.ok) throw new ApiError(response.status, 'CSRF_UNAVAILABLE', '')
  return (await response.json()) as { token: string; headerName: string }
}

/** 로그인 · 로그아웃으로 세션이 바뀌면 CSRF 토큰을 다시 받는다. */
export function resetCsrf() {
  csrf = null
}

// 서버는 POST · PUT · DELETE 요청에 CSRF 토큰 헤더를 요구한다
const csrfMiddleware: Middleware = {
  async onRequest({ request }) {
    if (SAFE_METHODS.has(request.method)) return request
    csrf ??= fetchCsrf().catch((error: unknown) => {
      csrf = null
      throw error
    })
    const { token, headerName } = await csrf
    request.headers.set(headerName, token)
    return request
  },
}

api.use(csrfMiddleware)

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, detail: string) {
    super(detail || code)
    this.status = status
    this.code = code
  }
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response }

/** openapi-fetch 결과에서 data를 꺼낸다. 실패하면 서버의 problem+json code를 담아 던진다. */
export async function unwrap<T>(request: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await request
  if (!response.ok) {
    const problem = (error ?? {}) as { code?: string; detail?: string }
    throw new ApiError(response.status, problem.code ?? 'UNKNOWN', problem.detail ?? '')
  }
  return data as T
}

const MESSAGES: Record<string, string> = {
  // AI 서버 오류는 '다시 시도'만으로 해결되지 않을 수 있어 계속될 때 할 일까지 알려 준다
  AI_UNAVAILABLE:
    'AI 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요. 계속되면 관리자에게 AI 서버 상태 확인을 요청해 주세요.',
  INTERNAL_ERROR: '서버에서 오류가 났어요. 잠시 후 다시 시도하고, 계속되면 관리자에게 알려 주세요.',
  ALREADY_APPLIED: '이 이메일로 이미 지원했어요.',
  POSTING_NOT_OPEN: '지금은 지원을 받지 않는 공고예요. 접수 기간을 확인해 주세요.',
  INVALID_PERIOD: '접수 기간을 확인해 주세요. 마감은 시작보다 뒤여야 해요.',
  RECRUITMENT_LOCKED:
    '공고 게시 중이거나 전형 진행 중에는 수정하거나 삭제할 수 없어요. 목록을 새로고침해 주세요.',
  ANSWER_CONFLICT:
    '다른 곳에서 답변이 변경됐어요. 작성한 내용을 보관하고 최신 답변을 다시 확인해 주세요.',
  UPDATE_CONFLICT: '기록이 변경됐어요. 최신 내용을 확인해 주세요.',
  BLIND_CONDITION:
    '블라인드 채용이라 자격 요건 · 우대 사항에 학력이나 출신 학교 조건을 쓸 수 없어요. 공고 작성에서 고쳐 주세요.',
  ANSWER_VERSION_REQUIRED: '최신 질문을 다시 불러온 뒤 저장해 주세요.',
  INTERVIEW_ACCESS_DENIED: '배정된 면접관만 본인 담당 질문을 수정할 수 있어요.',
  INTERVIEW_SCHEDULE_FAILED: '면접 일정을 배정하지 못했어요. 날짜를 확인한 뒤 다시 시도해 주세요.',
  INTERVIEW_SCHEDULE_DATE_REQUIRED:
    '전형 결과 화면의 다음 전형 안내에서 면접 날짜를 설정해 주세요.',
  INTERVIEW_SCHEDULE_PAST: '면접 시작일이 지났어요. 다음 전형의 면접 시작일을 다시 선택해 주세요.',
  INTERVIEW_SCHEDULE_CAPACITY:
    '다음 전형 시작 전까지 배정할 시간이 부족해요. 전형 안내 날짜를 조정해 주세요.',
  INTERVIEW_SCHEDULE_CLOSED: '이미 결과를 확정한 면접에는 일정을 자동 배정할 수 없어요.',
  INTERVIEW_ASSIGNMENT_CONFLICT:
    '기존 지원자별 면접관 배정이 서로 달라요. 면접 기록을 확인한 뒤 전형 공통 면접관을 설정해 주세요.',
  STAGE_NOT_ACTIVE: '진행 중인 전형에서만 바꿀 수 있어요.',
  QUESTIONS_PREPARING: '질문 준비가 끝나면 면접을 시작할 수 있어요.',
  INTERVIEW_NOT_RUNNING: '면접 진행 중에만 기록할 수 있어요.',
  INTERVIEW_STARTED: '면접이 시작되어 배정, 질문 구성이나 일정을 바꿀 수 없어요.',
  INTERVIEW_IN_PROGRESS: '진행 중인 면접을 모두 종료한 뒤 전형 결과를 확정해 주세요.',
  QUESTION_ANSWERED: '답변이 기록된 질문의 담당 변경이나 삭제는 할 수 없어요.',
  SESSION_CONFLICT: '면접 정보가 변경됐어요. 최신 내용을 확인해 주세요.',
  MEMO_CONFLICT:
    '본인의 메모가 다른 화면에서 변경됐어요. 작성한 내용을 보관하고 최신 메모를 확인해 주세요.',
  QUESTION_OWNER_REQUIRED: '질문의 인사·실무 담당을 먼저 지정해 주세요.',
  INVALID_INTERVIEWER: '같은 기업의 계정만 면접관으로 배정할 수 있어요.',
  DISTINCT_INTERVIEWERS: '인사 면접관과 실무 면접관은 서로 다른 계정으로 배정해 주세요.',
  STAGE_CLOSED: '결과를 확정한 전형이라 바꿀 수 없어요.',
  INTERVIEW_NOT_STARTED: '두 면접관이 모두 [준비 완료]를 눌러 면접을 시작한 뒤에 할 수 있어요.',
  INTERVIEW_ENDED: '종료한 면접이에요.',
  INTERVIEW_NOT_SCHEDULED: '면접 일시가 정해져야 면접을 시작할 수 있어요.',
  INTERVIEW_SLOT_STARTED: '이미 시작한 면접 시간이에요. 다른 시간을 골라 주세요.',
  INTERVIEW_ANSWERED: '답변을 기록한 지원자는 불참으로 표시할 수 없어요.',
  INTERVIEW_NOT_ENDED: '내 면접을 종료한 뒤에 의견을 남길 수 있어요.',
  INTERVIEW_ABSENT: '불참한 지원자에게는 의견을 남기지 않아요.',
  INTERVIEWERS_READY:
    '면접관이 준비 완료해 질문을 다시 만들 수 없어요. 준비를 취소한 뒤 다시 요청해 주세요.',

  INVALID_CREDENTIALS: '이메일이나 비밀번호가 맞지 않아요.',
  EMAIL_ALREADY_EXISTS: '이미 가입한 이메일이에요.',
  INVALID_INPUT: '입력한 내용을 다시 확인해 주세요.',
  INVALID_FILE: 'PDF 파일만 올릴 수 있어요.',
  POSTER_TEMPLATE_CONFLICT: '같은 이름의 템플릿이 있거나 저장 가능한 12개를 채웠어요.',
  CANVA_NOT_CONNECTED: '설정 → 채용 공고에서 Canva 계정을 먼저 연결해 주세요.',
  CANVA_UNAVAILABLE: 'Canva 작업을 완료하지 못했어요. 계정 권한과 연결 상태를 확인해 주세요.',
  CANVA_EXPORT_UNAVAILABLE:
    '현재 계정에서 내보낼 수 있는 디자인만 가져올 수 있어요. 유료 요소와 이용 한도를 확인해 주세요.',
  CANVA_COPY_FAILED: 'Canva 작업본을 만들지 못했어요. 디자인 접근 권한을 확인해 주세요.',
  CANVA_READ_FAILED: 'Canva 디자인의 편집 영역을 읽지 못했어요.',
  CANVA_PREVIEW_FAILED: 'Canva 디자인 배경을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.',
  CANVA_IMAGE_FAILED: 'Canva 배경 이미지가 너무 크거나 지원하지 않는 형식이에요.',
  UNAUTHENTICATED: '다시 로그인해 주세요.',
  FORBIDDEN: '이 작업을 할 권한이 없어요.',
  INVALID_CSRF: '보안 토큰이 만료됐어요. 다시 시도해 주세요.',
  ANALYSIS_NOT_FAILED: '이미 분석 중이거나 분석이 끝난 지원자예요.',
  NOTICES_NOT_SENT: '합격·불합격 안내를 모두 먼저 보내 주세요.',
  REPORT_DOCUMENT_ONLY:
    '비교 · 전형 결과 리포트는 서류 전형에서만 만들어요. 전형 흐름은 채용 최종 리포트에서 볼 수 있어요.',
}

/** 화면에 보여 줄 오류 문구. 모르는 오류는 일반 문구로 바꾼다. */
export function errorMessage(
  error: unknown,
  fallback = '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.',
) {
  if (error instanceof ApiError) {
    if (error.code === 'INVALID_CSRF') resetCsrf()
    return MESSAGES[error.code] ?? fallback
  }
  return fallback
}
