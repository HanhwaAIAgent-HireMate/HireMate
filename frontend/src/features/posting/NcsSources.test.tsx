import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { NcsSource } from '@/features/posting/api'

import { NcsSources } from './NcsSources'

function source(overrides: Partial<NcsSource>): NcsSource {
  return {
    field: 'duties',
    number: 1,
    line: '결제 · 정산 서비스의 배치 프로그램을 구현합니다',
    dutyName: '응용SW엔지니어링',
    unitCode: '2001020211_23v6',
    unitName: '서버프로그램 구현',
    taskName: '배치 프로그램 구현하기',
    sentence: '애플리케이션 설계를 기반으로 배치 프로그램을 구현 한다',
    ...overrides,
  }
}

describe('참고한 NCS', () => {
  it('출처가 없으면 아무것도 보이지 않는다', () => {
    const { container } = render(<NcsSources sources={[]} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('공고 줄, NCS 경로, 원문을 화면 순서로 보인다', () => {
    render(
      <NcsSources
        sources={[
          source({ field: 'preferred', number: 1, line: '모듈 설계 경험' }),
          source({ field: 'duties', number: 3, line: '장애 원인을 분석합니다' }),
          source({ field: 'duties', number: 2 }),
        ]}
      />,
    )

    expect(screen.getByText('참고한 NCS 3건')).toBeInTheDocument()
    const items = screen.getAllByTestId('ncs-source')
    expect(
      items.map((item) => within(item).getByText(/^(주요 업무|우대 사항) \d$/).textContent),
    ).toEqual(['주요 업무 2', '주요 업무 3', '우대 사항 1'])
    expect(
      within(items[0]).getByText('응용SW엔지니어링 › 서버프로그램 구현 › 배치 프로그램 구현하기'),
    ).toBeInTheDocument()
    expect(
      within(items[0]).getByText('애플리케이션 설계를 기반으로 배치 프로그램을 구현 한다'),
    ).toBeInTheDocument()
  })

  it('처음에는 펼쳐 두고 제목을 누르면 접는다', () => {
    render(<NcsSources sources={[source({})]} />)
    const details = screen.getByText('참고한 NCS 1건').closest('details')

    expect(details).toHaveAttribute('open')
    fireEvent.click(screen.getByText('참고한 NCS 1건'))
    expect(details).not.toHaveAttribute('open')
  })
})
