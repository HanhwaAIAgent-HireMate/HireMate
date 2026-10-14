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
  INVALID_CREDENTIALS: '이메일이나 비밀번호가 맞지 않아요.',
  EMAIL_ALREADY_EXISTS: '이미 가입한 이메일이에요.',
  INVALID_INPUT: '입력한 내용을 다시 확인해 주세요.',
  INVALID_FILE: 'PDF 파일만 올릴 수 있어요.',
  UNAUTHENTICATED: '다시 로그인해 주세요.',
  FORBIDDEN: '이 작업을 할 권한이 없어요.',
  INVALID_CSRF: '보안 토큰이 만료됐어요. 다시 시도해 주세요.',
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
