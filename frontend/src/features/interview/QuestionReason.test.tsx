import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { QuestionReason } from './QuestionReason'

describe('질문 생성 근거', () => {
  it('버튼을 누르면 저장된 근거가 열리고 다시 누르면 접힌다', () => {
    render(
      <QuestionReason
        text="담당한 역할을 설명해 주세요."
        source="AI"
        reason={'출처: 이력서\n원문: 결제 API 개발'}
      />,
    )
    const button = screen.getByRole('button', { name: '질문 생성 근거' })

    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('region')).toHaveTextContent('근거')
    expect(screen.getByRole('region')).toHaveTextContent('결제 API 개발')
    expect(screen.getByRole('region').querySelector('blockquote')).toHaveTextContent(
      '결제 API 개발',
    )
    fireEvent.click(button)
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })

  it.each(['AI', 'MANUAL'] as const)('근거가 없는 %s 질문은 출처를 꾸며내지 않는다', (source) => {
    render(<QuestionReason text="이전 질문" source={source} reason={null} />)
    fireEvent.click(screen.getByRole('button', { name: '질문 생성 근거' }))
    expect(screen.getByRole('region')).toHaveTextContent(
      source === 'AI' ? '생성 근거가 저장되기 전에' : '담당자가 직접 추가한 질문',
    )
  })

  it('질문마다 열림 상태를 독립적으로 유지한다', () => {
    render(
      <>
        <QuestionReason text="1차 질문" source="AI" reason="이력서 근거" />
        <QuestionReason text="최종 질문" source="AI" reason="조직 문화 기준" />
      </>,
    )
    fireEvent.click(screen.getAllByRole('button', { name: '질문 생성 근거' })[1])
    expect(screen.getByRole('region')).toHaveTextContent('조직 문화 기준')
    expect(screen.getAllByRole('button')[0]).toHaveAttribute('aria-expanded', 'false')
  })

  it('원문 근거와 확인 목적을 구분하고 최종면접 자리와 이전 질문도 표시한다', () => {
    render(
      <QuestionReason
        text="이전 경험을 설명해 주세요."
        source="AI"
        reason={
          '이 질문의 자리: 1차 미확인\n질문 기준: 본인 역할\n질문 유형: 이전 면접에서 확인 안 됨\n확인할 내용: 설계 판단의 근거 확인\n이전 면접 질문: 역할을 설명해 주세요.\n출처: 이력서\n원문: 결제 API를 개발했습니다.'
        }
      />,
    )
    expect(screen.getByLabelText('질문 유형: 이전 면접에서 확인 안 됨')).toBeVisible()
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '질문 생성 근거' }))
    const region = screen.getByRole('region')
    for (const label of ['근거', '면접 확인 부분', '이전 면접 질문'])
      expect(region).toHaveTextContent(label)
    expect(screen.getByLabelText('이 질문의 자리: 1차 미확인')).toHaveClass('rounded-full')
    expect(region.querySelector('blockquote')).toHaveTextContent('결제 API를 개발했습니다.')
    expect(region).not.toHaveTextContent('왜 이 질문인가요')
    expect(region).not.toHaveTextContent('지원서 원문')
    expect(region.querySelector('blockquote')?.parentElement).toHaveTextContent('이력서')
    expect(region.textContent.indexOf('결제 API를 개발했습니다.')).toBeLessThan(
      region.textContent.indexOf('설계 판단의 근거 확인'),
    )
  })

  it('자기소개에는 실제 문서 근거 대신 공통 질문의 목적을 보여준다', () => {
    render(<QuestionReason text="1분 자기소개 부탁드립니다." source="AI" reason={null} />)
    fireEvent.click(screen.getByRole('button', { name: '질문 생성 근거' }))
    expect(screen.getByRole('region')).toHaveTextContent('이 전형의 모든 지원자에게')
    expect(screen.getByRole('region')).not.toHaveTextContent('생성 근거가 저장되기 전에')
  })

  it('원문이 없으면 저장된 기준을 보여주고 같은 확인 목적을 반복하지 않는다', () => {
    render(
      <QuestionReason
        text="경험을 설명해 주세요."
        source="AI"
        reason={'질문 기준: API 설계 경험\n확인할 내용: API 설계 경험\n질문 유형: 필수조건 확인'}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '질문 생성 근거' }))
    const region = screen.getByRole('region')
    expect(region.textContent?.match(/API 설계 경험/g)).toHaveLength(1)
    expect(region).toHaveTextContent('구체적인 확인 목적은 별도로 기록되지 않았습니다.')
    expect(region.querySelector('blockquote')).not.toBeInTheDocument()
  })

  it('Windows 줄바꿈이 섞인 원문도 출처와 인용문으로 나눈다', () => {
    render(
      <QuestionReason
        text="경험을 설명해 주세요."
        source="AI"
        reason={'출처: 자기소개서\n원문: 야간 배치의 종료 시간이\r\n들쑥날쑥했습니다.'}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '질문 생성 근거' }))
    expect(screen.getByRole('region').querySelector('blockquote')).toHaveTextContent(
      '야간 배치의 종료 시간이 들쑥날쑥했습니다.',
    )
  })
})
