import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { PosterMotion } from './PosterMotion'
import { exportPosterPdf } from './poster-design'

it('웹 장식은 일시정지와 재생이 가능하고 NONE에서는 장식과 버튼을 표시하지 않는다', () => {
  const { container, rerender } = render(<PosterMotion effect="GLOW" />)
  fireEvent.click(screen.getByRole('button', { name: '포스터 움직임 일시정지' }))
  expect(container.querySelector('.poster-motion')).toHaveAttribute('data-paused', 'true')
  fireEvent.click(screen.getByRole('button', { name: '포스터 움직임 재생' }))
  expect(container.querySelector('.poster-motion')).toHaveAttribute('data-paused', 'false')
  rerender(<PosterMotion effect="NONE" />)
  expect(container).toBeEmptyDOMElement()
  rerender(<PosterMotion effect="WAVE" />)
  expect(container).toBeEmptyDOMElement()
})

it('PDF 복제는 정지 상태로 인쇄하며 재생 버튼을 제거하고 원본 웹 장식은 유지한다', async () => {
  const print = vi.fn()
  const append = document.body.append.bind(document.body)
  const appended = vi.spyOn(document.body, 'append').mockImplementation((...nodes) => {
    append(...nodes)
    for (const node of nodes) {
      if (node instanceof HTMLIFrameElement && node.contentWindow) {
        node.contentWindow.print = print
        node.contentWindow.focus = vi.fn()
        Object.defineProperty(node.contentDocument, 'fonts', {
          value: { ready: Promise.resolve() },
        })
      }
    }
  })
  const timer = vi.spyOn(window, 'setTimeout').mockReturnValue(0)
  const element = document.createElement('article')
  element.className = 'posting-poster'
  const { container, unmount } = render(<PosterMotion effect="GLOW" />, { container: element })
  const video = document.createElement('div')
  video.className = 'poster-video-region'
  video.append(document.createElement('video'))
  container.append(video)
  try {
    await exportPosterPdf(container, '공고 테스트')
    const frame = document.querySelector<HTMLIFrameElement>('iframe[title="공고 PDF 출력"]')!
    expect(
      frame.contentDocument!.querySelector('.posting-poster')?.getAttribute('data-poster-static'),
    ).toBe('true')
    expect(frame.contentDocument!.querySelector('.poster-motion-control')).toBeNull()
    expect(frame.contentDocument!.querySelector('video')).toBeNull()
    expect(container.querySelector('video')).not.toBeNull()
    expect(frame.contentDocument!.querySelector('.poster-motion-glow')).not.toBeNull()
    expect(container.querySelector('.poster-motion-control')).not.toBeNull()
    expect(print).toHaveBeenCalledOnce()
    frame.remove()
  } finally {
    unmount()
    appended.mockRestore()
    timer.mockRestore()
  }
})
