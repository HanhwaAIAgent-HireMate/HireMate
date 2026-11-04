import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ReportDistribution } from './api'
import { insightLines } from './distribution'
import { DistributionView } from './DistributionView'

const person = (id: string, name: string) => ({
  applicationId: id,
  name,
  careerYears: 3,
  metCount: 8,
  criterionTotal: 10,
  talentCount: 0,
  unknownCount: 1,
  partialCount: 0,
  missingRequired: [],
})

const distribution: ReportDistribution = {
  stageId: 's',
  total: 300,
  analyzed: 300,
  aboveLine: 80,
  target: 60,
  defaultTarget: 60,
  hireCount: 6,
  targetMultiplier: 10,
  sort: 'BASIC',
  required: { met: 80, unmet: 150, unknown: 70, criterionIds: ['Q-01'] },
  criteria: [
    {
      criterionId: 'Q-01',
      category: 'QUALIFICATION',
      text: 'Java 서버 개발 경력 3년 이상',
      required: true,
      met: 80,
      partial: 0,
      notMet: 150,
      unknown: 70,
    },
  ],
  counts: [
    { value: 9, count: 50 },
    { value: 8, count: 30 },
  ],
  cut: { value: 8, from: 51, to: 80, inside: 10 },
  groups: [
    {
      id: 'selection-edge',
      label: '선발 경계',
      reason: '목표 60명째와 개수가 같아요',
      people: Array.from({ length: 7 }, (_, index) => person(`p${index}`, `지원자${index}`)),
    },
  ],
  deepSize: 5,
  careers: [{ label: '신입', all: 10, aboveLine: 2 }],
  passed: null,
}

const query = vi.hoisted(() => ({ target: [] as (number | null)[] }))

vi.mock('./EChart', () => ({
  EChart: ({ label }: { label: string }) => <div role="img" aria-label={label} />,
}))

vi.mock('./api', () => ({
  useReportDistribution: (_stageId: string, target: number | null) => {
    query.target.push(target)
    return { data: distribution, isError: false, isFetching: false }
  },
  useDistributionNote: () => ({
    data: {
      lines: ['Java · Kotlin 경력은 확인 필요가 많아 서류만으로 거르기 어려워요.'],
      charts: { counts: '충족 8개인 30명 사이에서 목표가 갈려요.' },
    },
    isLoading: false,
  }),
}))

describe('분포 리포트', () => {
  it('숫자 요약 아래 AI 해설을 따로 보여 준다', () => {
    render(<DistributionView stageId="s" onDeepDive={() => {}} deepPending={false} />)

    expect(screen.getByText('◇ AI 해설')).toBeInTheDocument()
    expect(
      screen.getByText('Java · Kotlin 경력은 확인 필요가 많아 서류만으로 거르기 어려워요.'),
    ).toBeInTheDocument()
    // 차트마다 Report Agent의 해석을 그 차트 아래에 붙인다
    expect(screen.getByText('충족 8개인 30명 사이에서 목표가 갈려요.')).toBeInTheDocument()
    expect(screen.getAllByText('◇ AI 해석')).toHaveLength(1)
  })

  it('목표 인원에서 개수가 같은 구간을 글로 알려 준다', () => {
    render(<DistributionView stageId="s" onDeepDive={() => {}} deepPending={false} />)

    expect(screen.getByText(/51~80번째 30명이 모두 8개라/)).toBeInTheDocument()
  })

  it('다시 볼 지원자는 한 번에 5명씩 비교를 요청한다', () => {
    const onDeepDive = vi.fn()
    render(<DistributionView stageId="s" onDeepDive={onDeepDive} deepPending={false} />)

    fireEvent.click(screen.getByRole('button', { name: '이 5명 비교' }))
    expect(onDeepDive).toHaveBeenCalledWith(['p0', 'p1', 'p2', 'p3', 'p4'])

    expect(screen.getByRole('button', { name: /이전 5명/ })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /다음 5명/ }))
    fireEvent.click(screen.getByRole('button', { name: '이 2명 비교' }))
    expect(onDeepDive).toHaveBeenLastCalledWith(['p5', 'p6'])
    expect(screen.getByRole('button', { name: /다음 5명/ })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /이전 5명/ }))
    fireEvent.click(screen.getByRole('button', { name: '이 5명 비교' }))
    expect(onDeepDive).toHaveBeenLastCalledWith(['p0', 'p1', 'p2', 'p3', 'p4'])
  })

  it('합격 처리가 목표를 넘으면 막지 않고 차이를 알려 준다', () => {
    expect(insightLines({ ...distribution, passed: 65 })).toContain(
      '합격 처리 65명으로 목표 60명보다 5명 많아요. 목표는 참고값이라 합격을 막지 않아요.',
    )
    expect(insightLines({ ...distribution, passed: 12 })).toContain(
      '합격 처리 12명으로 목표 60명까지 48명 남았어요.',
    )
  })

  it('맨 위 요약을 숫자로 만든다', () => {
    expect(insightLines(distribution)).toEqual([
      '필수 조건을 모두 충족한 80명이 목표 60명보다 20명 많아요. 충족 8개인 30명 사이에서 선발이 갈려요.',
      "가장 많이 걸리는 필수 조건은 'Java 서버 개발 경력 3년 이상'(Q-01)이에요. 73%가 충족이 아니에요(미충족 · 부분 50%, 확인 필요 23%).",
    ])
  })

  it('목표 인원을 바꾸면 그 인원으로 다시 센다', () => {
    render(<DistributionView stageId="s" onDeepDive={() => {}} deepPending={false} />)

    const input = screen.getByRole('textbox', { name: '서류 통과 목표 인원' })
    fireEvent.change(input, { target: { value: '40' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(query.target.at(-1)).toBe(40)
  })
})
