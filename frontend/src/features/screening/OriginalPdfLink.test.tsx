import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { OriginalPdfLink } from '@/features/screening/OriginalPdfLink'

afterEach(() => vi.unstubAllGlobals())

describe('원본 PDF 열기', () => {
  it('가린 정보가 없으면 바로 여는 링크다', () => {
    render(<OriginalPdfLink href="/doc" hidden={[]} />)
    expect(screen.getByRole('link', { name: '원본 PDF' })).toHaveAttribute('href', '/doc')
  })

  it('가린 정보가 있으면 무엇이 보이는지 알리고, 열기를 고르면 연다', () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)
    render(<OriginalPdfLink href="/doc" hidden={['출신 학교', '학점']} />)
    fireEvent.click(screen.getByRole('button', { name: '원본 PDF' }))
    expect(screen.getByText(/블라인드로 가린 출신 학교 · 학점이 그대로 있어요/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '열기' }))
    expect(open).toHaveBeenCalledWith('/doc', '_blank', 'noreferrer')
  })

  it('조사를 마지막 낱말에 맞춘다', () => {
    render(<OriginalPdfLink href="/doc" hidden={['출신 학교']} />)
    fireEvent.click(screen.getByRole('button', { name: '원본 PDF' }))
    expect(screen.getByText(/출신 학교가 그대로 있어요/)).toBeInTheDocument()
  })
})
