import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { OriginalPdfLink } from '@/features/screening/OriginalPdfLink'

describe('원본 PDF 열기', () => {
  it('묻지 않고 바로 여는 링크다', () => {
    render(<OriginalPdfLink href="/doc" />)
    expect(screen.getByRole('link', { name: '원본 PDF' })).toHaveAttribute('href', '/doc')
    expect(screen.queryByText('원본에는 이름이 보여요')).not.toBeInTheDocument()
  })

  it('원본에 이름이 있으면 이름이 보인다고 안내한다', () => {
    render(<OriginalPdfLink href="/doc" showsName />)
    expect(screen.getByText('원본에는 이름이 보여요')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '원본 PDF' })).toHaveAttribute('href', '/doc')
  })
})
