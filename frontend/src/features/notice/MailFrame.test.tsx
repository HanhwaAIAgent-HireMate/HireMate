import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MailFrame } from './MailFrame'

describe('MailFrame', () => {
  it('backend가 만든 메일 HTML을 스크립트를 막은 iframe에 그대로 넣고 제목을 함께 보여 준다', () => {
    const html = '<!doctype html><html><body><p>홍길동님, 감사합니다.</p></body></html>'
    render(
      <MailFrame preview={{ subject: '[예시 기업] 서류 전형 결과 안내', html }} title="미리보기" />,
    )

    expect(screen.getByText('[예시 기업] 서류 전형 결과 안내')).toBeInTheDocument()
    const frame = screen.getByTitle('미리보기')
    expect(frame).toHaveAttribute('srcdoc', html)
    expect(frame).toHaveAttribute('sandbox', 'allow-same-origin')
  })

  it('메일을 받기 전에는 iframe 대신 자리만 보여 준다', () => {
    render(<MailFrame preview={undefined} title="미리보기" />)

    expect(screen.queryByTitle('미리보기')).not.toBeInTheDocument()
  })
})
