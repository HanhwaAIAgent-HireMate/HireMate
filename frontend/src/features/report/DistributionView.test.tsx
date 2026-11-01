import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ReportDistribution } from './api'
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
}

const query = vi.hoisted(() => ({ target: [] as (number | null)[] }))

vi.mock('./api', () => ({
  useReportDistribution: (_stageId: string, target: number | null) => {
    query.target.push(target)
    return { data: distribution, isError: false, isFetching: false }
  },
}))

describe('분포 리포트', () => {
  it('목표 인원에서 개수가 같은 구간을 글로 알려 준다', () => {
    render(<DistributionView stageId="s" onDeepDive={() => {}} deepPending={false} />)

    expect(screen.getByText(/51~80번째 30명이 모두 8개라/)).toBeInTheDocument()
  })

  it('경계 그룹은 한 번에 5명씩 심층 분석을 요청한다', () => {
    const onDeepDive = vi.fn()
    render(<DistributionView stageId="s" onDeepDive={onDeepDive} deepPending={false} />)

    fireEvent.click(screen.getByRole('button', { name: '이 5명 심층 분석' }))
    expect(onDeepDive).toHaveBeenCalledWith(['p0', 'p1', 'p2', 'p3', 'p4'])

    fireEvent.click(screen.getByRole('button', { name: /다음 5명/ }))
    fireEvent.click(screen.getByRole('button', { name: '이 2명 심층 분석' }))
    expect(onDeepDive).toHaveBeenLastCalledWith(['p5', 'p6'])
  })

  it('목표 인원을 바꾸면 그 인원으로 다시 센다', () => {
    render(<DistributionView stageId="s" onDeepDive={() => {}} deepPending={false} />)

    const input = screen.getByRole('textbox', { name: '서류 통과 목표 인원' })
    fireEvent.change(input, { target: { value: '40' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(query.target.at(-1)).toBe(40)
  })
})
