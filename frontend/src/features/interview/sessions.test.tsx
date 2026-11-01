import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import {
  sessionKeys,
  useAssignStageInterview,
  useMyInterviews,
  useStageInterviewAssignment,
} from './sessions'
import { resetCsrf } from '@/lib/api/client'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  resetCsrf()
})

it('내 면접 목록은 다른 화면에서 면접을 시작해도 주기적으로 상태를 새로 읽는다', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  let status = 'SCHEDULED'
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      Response.json({
        items: [
          {
            stageId: 'stage',
            applicationId: 'kim',
            recruitmentTitle: '채용',
            stageName: '면접',
            applicantName: '김지원',
            schedule: null,
            myRole: 'HR',
            status,
            recruitmentId: 'recruit',
          },
        ],
        total: 1,
        page: 0,
        size: 50,
      }),
    ),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useMyInterviews(), { wrapper })
  await waitFor(() => expect(hook.result.current.data?.items[0].status).toBe('SCHEDULED'))
  status = 'IN_PROGRESS'
  await act(() => vi.advanceTimersByTimeAsync(5_100))
  expect(hook.result.current.data?.items[0].status).toBe('IN_PROGRESS')
  hook.unmount()
  client.clear()
})

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

const common = {
  stageId: 'stage',
  hrMemberId: 'hr',
  practicalMemberId: 'practical',
  version: 2,
  locked: false,
}

it('지원자 없이도 전형 공통 배정을 조회한다', async () => {
  const requests: string[] = []
  vi.stubGlobal('fetch', (request: Request) => {
    requests.push(new URL(request.url).pathname)
    return Promise.resolve(Response.json(common))
  })
  const { client, wrapper } = setup()
  const hook = renderHook(() => useStageInterviewAssignment('stage'), { wrapper })
  await waitFor(() => expect(hook.result.current.data).toEqual(common))
  expect(requests).toEqual(['/api/stages/stage/interview/assignment'])
  hook.unmount()
  client.clear()
})

it('공통 배정을 한 번 저장하면 전형의 모든 지원자 캐시를 갱신한다', async () => {
  const requests: { url: string; body: unknown }[] = []
  vi.stubGlobal('fetch', async (request: Request | string) => {
    if (typeof request === 'string')
      return Response.json({ token: 't', headerName: 'X-CSRF-TOKEN' })
    requests.push({ url: new URL(request.url).pathname, body: await request.json() })
    return Response.json(common)
  })
  const { client, wrapper } = setup()
  const keys = [
    sessionKeys.workspace('stage', 'one'),
    sessionKeys.workspace('stage', 'two'),
    sessionKeys.assignment('stage', 'one'),
    sessionKeys.assignment('stage', 'two'),
    sessionKeys.progress('stage'),
    sessionKeys.mine,
  ]
  keys.forEach((key) => client.setQueryData(key, {}))
  client.setQueryData(sessionKeys.workspace('other', 'one'), {})
  const hook = renderHook(() => useAssignStageInterview('stage'), { wrapper })
  const body = { hrMemberId: 'hr', practicalMemberId: 'practical', expectedVersion: 1 }
  await act(() => hook.result.current.mutateAsync(body))
  expect(requests).toEqual([{ url: '/api/stages/stage/interview/assignment', body }])
  expect(client.getQueryData(sessionKeys.stageAssignment('stage'))).toEqual(common)
  keys.forEach((key) => expect(client.getQueryState(key)?.isInvalidated).toBe(true))
  expect(client.getQueryState(sessionKeys.workspace('other', 'one'))?.isInvalidated).toBe(false)
  hook.unmount()
  client.clear()
})

it('공통 배정된 지원자가 50명을 넘어도 모든 페이지를 읽는다', async () => {
  const pages: number[] = []
  vi.stubGlobal('fetch', (request: Request) => {
    const page = Number(new URL(request.url).searchParams.get('page'))
    pages.push(page)
    return Promise.resolve(
      Response.json({
        items: Array.from({ length: page === 0 ? 50 : 1 }, (_, index) => ({
          stageId: 'stage',
          applicationId: `candidate-${page * 50 + index}`,
          recruitmentTitle: '채용',
          stageName: '면접',
          applicantName: `지원자 ${page * 50 + index}`,
          schedule: null,
          myRole: 'HR',
          status: 'SCHEDULED',
          recruitmentId: 'recruit',
        })),
        total: 51,
        page,
        size: 50,
      }),
    )
  })
  const { client, wrapper } = setup()
  const hook = renderHook(() => useMyInterviews(), { wrapper })
  await waitFor(() => expect(hook.result.current.data?.items).toHaveLength(51))
  expect(hook.result.current.data?.items[50].applicationId).toBe('candidate-50')
  expect(pages).toEqual([0, 1])
  hook.unmount()
  client.clear()
})
