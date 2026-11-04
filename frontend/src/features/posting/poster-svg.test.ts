import { expect, it, vi } from 'vitest'
import { inlinePosterSvg, loadPosterFonts, POSTER_FONT } from './poster-svg'

it('한글과 숫자를 실제 출력 글꼴로 먼저 로드한 뒤 측정한다', async () => {
  const previous = document.fonts
  const load = vi.fn().mockResolvedValue([])
  Object.defineProperty(document, 'fonts', {
    configurable: true,
    value: { load, ready: Promise.resolve() },
  })
  try {
    await loadPosterFonts('1967년 개인·기업 금융을 제공합니다')
    expect(load).toHaveBeenCalledWith(
      `400 16px "${POSTER_FONT}"`,
      '1967년 개인·기업 금융을 제공합니다',
    )
    expect(load).toHaveBeenCalledWith(
      `700 16px "${POSTER_FONT}"`,
      '1967년 개인·기업 금융을 제공합니다',
    )
  } finally {
    Object.defineProperty(document, 'fonts', { configurable: true, value: previous })
  }
})

it('문서 안에서 같은 글꼴을 사용하는 벡터로 출력하고 외부 실행 요소를 거절한다', () => {
  const svg = inlinePosterSvg(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800"><text>회사 소개</text></svg>',
  )
  expect(svg).toContain('viewBox="0 0 600 800"')
  expect(svg).toContain('width="100%"')
  expect(svg).toContain('회사 소개')
  expect(() =>
    inlinePosterSvg('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'),
  ).toThrow()
  expect(() =>
    inlinePosterSvg(
      '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.com/a.png"/></svg>',
    ),
  ).toThrow()
})
