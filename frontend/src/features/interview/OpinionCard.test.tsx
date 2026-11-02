import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { OpinionCard, OpinionLine } from '@/features/interview/OpinionCard'
import { formatDateTime } from '@/lib/format'

const slot = (role: string, mine: boolean, extra: object = {}) => ({
  memberId: role,
  name: '',
  role,
  submitted: false,
  recommendation: null,
  comment: null,
  updatedAt: null,
  edited: false,
  mine,
  unassigned: false,
  ...extra,
})

function mockServer() {
  const puts: unknown[] = []
  let opinions = [slot('PRACTICAL', true), slot('HR', false, { submitted: true, name: '최은영' })]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: Request | string) => {
      if (typeof input === 'string')
        return Response.json({ token: 't', headerName: 'X-CSRF-TOKEN', parameterName: '_csrf' })
      if (input.method === 'PUT') {
        const body: unknown = await input.clone().json()
        puts.push(body)
        opinions = [
          slot('PRACTICAL', true, {
            ...(body as object),
            submitted: true,
            updatedAt: '2026-11-01T03:00:00Z',
          }),
          slot('HR', false, {
            submitted: true,
            name: '최은영',
            recommendation: 'RECOMMEND',
            comment: '협업 경험을 구체적으로 설명함',
          }),
        ]
      }
      return Response.json(opinions)
    }),
  )
  return puts
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('OpinionCard', () => {
  it.each([
    [false, '작성됨'],
    [true, '수정됨'],
  ] as const)('의견의 최초 저장과 수정 시각을 구분한다: %s', (edited, label) => {
    const updatedAt = '2026-11-02T01:40:00Z'
    render(
      <OpinionLine
        opinion={{
          memberId: 'hr',
          name: '최인사',
          role: 'HR',
          submitted: true,
          recommendation: 'RECOMMEND',
          comment: '협업 경험 확인',
          updatedAt,
          edited,
          mine: false,
          unassigned: false,
        }}
        scrollable
      />,
    )
    expect(screen.getByText(`${label} · ${formatDateTime(updatedAt)}`)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '인사 · 최인사 의견 내용' })).toHaveTextContent(
      '협업 경험 확인',
    )
  })

  it('다른 면접관 의견은 잠겨 있다가 내 의견을 저장하면 열린다', async () => {
    const puts = mockServer()
    render(
      <QueryClientProvider client={createQueryClient()}>
        <OpinionCard stageId="s1" applicationId="a1" editable />
      </QueryClientProvider>,
    )

    expect(await screen.findByText(/내 의견을 저장하면 내용이 보여요/)).toBeInTheDocument()
    expect(
      screen.getByPlaceholderText(/나이 · 성별 · 출신 지역 · 혼인 여부 · 신체 조건은 쓰지 않아요/),
    ).toBeInTheDocument()
    const save = screen.getByRole('button', { name: '의견 저장' })
    expect(save).toBeDisabled()

    fireEvent.click(screen.getByRole('radio', { name: '보류' }))
    fireEvent.change(screen.getByLabelText('의견 이유'), {
      target: { value: '설계 판단 범위는 더 확인 필요' },
    })
    fireEvent.click(save)

    await vi.waitFor(() =>
      expect(puts).toEqual([{ recommendation: 'HOLD', comment: '설계 판단 범위는 더 확인 필요' }]),
    )
    expect(await screen.findByText('협업 경험을 구체적으로 설명함')).toBeInTheDocument()
  })
})
