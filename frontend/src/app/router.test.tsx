import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'

import { routes } from './router'

describe('routes', () => {
  it.each([
    ['/', '채용 대시보드'],
    ['/hr', '채용 대시보드'],
    ['/hr/settings', '설정'],
    ['/hr/recruitments/new', '공고 편집'],
    ['/hr/recruitments/1/posting', '공고 편집'],
    ['/hr/recruitments/1/stages/2', '공통 전형 화면'],
    ['/hr/recruitments/1/stages/2/close', '전형 종료'],
    ['/hr/recruitments/1/report', '채용 리포트'],
    ['/careers/1', '채용 공고'],
    ['/careers/1/apply', '지원서'],
  ])('%s 경로는 "%s" 화면을 연다', (path, title) => {
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)

    expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument()
  })
})
