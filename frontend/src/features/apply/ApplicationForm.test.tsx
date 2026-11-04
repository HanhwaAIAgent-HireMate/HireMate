import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApplicationForm } from '@/features/apply/ApplicationForm'
import type { PublicPosting } from '@/features/posting/api'
import { initialPoster } from '@/features/posting/poster-design'
import { resetCsrf } from '@/lib/api/client'

function posting(blind: boolean): PublicPosting {
  return {
    postingId: 'posting-1',
    companyName: '테스트 기업',
    content: {
      title: '백엔드 개발자',
      jobCategory: '개발',
      career: '신입',
      employmentType: '정규직',
      location: '서울',
      intro: '',
      duties: ['결제 API 개발'],
      qualifications: [],
      preferred: [],
      benefits: [],
      roles: [],
      headcount: 1,
      position: '',
      education: '',
      workHours: '',
      salary: '',
      blind,
    },
    notices: [],
    stages: [],
    documents: [],
    openAt: '2026-11-01T00:00:00Z',
    closeAt: '2026-12-01T00:00:00Z',
    state: 'OPEN',
    poster: initialPoster(),
    companyAddress: '',
  }
}

beforeEach(() => {
  resetCsrf()
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
})
afterEach(() => vi.unstubAllGlobals())

/** 지원서를 채우고 제출을 누른다. 학교 이름 확인 응답과 보낸 요청 경로를 돌려준다 */
function fillAndSubmit(blind: boolean, names: string[]) {
  const requests: string[] = []
  vi.stubGlobal('fetch', (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) {
      return Promise.resolve(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
    }
    requests.push(new URL(url, 'http://localhost').pathname)
    if (url.includes('/school-check')) {
      return Promise.resolve(
        Response.json({ documents: names.length ? [{ type: 'RESUME', names }] : [] }),
      )
    }
    return Promise.resolve(
      Response.json(
        {
          applicationNo: 1,
          name: '정유민',
          companyName: '테스트 기업',
          postingTitle: '백엔드 개발자',
        },
        { status: 201 },
      ),
    )
  })
  const onSubmitted = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ApplicationForm posting={posting(blind)} onSubmitted={onSubmitted} />
    </QueryClientProvider>,
  )
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '정유민' } })
  fireEvent.change(screen.getByLabelText('이메일'), { target: { value: 'a@example.com' } })
  fireEvent.change(screen.getByLabelText('연락처'), { target: { value: '010-0000-0000' } })
  for (const label of ['이력서', '자기소개서']) {
    const pdf = new File(['%PDF'], `${label}.pdf`, { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText(`${label} 파일`), { target: { files: [pdf] } })
  }
  fireEvent.click(screen.getByRole('checkbox', { name: '개인정보 수집·이용에 동의합니다.' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'AI 활용 안내를 확인했습니다.' }))
  fireEvent.click(screen.getByRole('button', { name: '제출하기' }))
  return { requests, onSubmitted }
}

describe('블라인드 채용 학교 이름 알림', () => {
  it('서류에 학교 이름이 있으면 알리고, 그대로 제출을 고르면 제출한다', async () => {
    const { requests, onSubmitted } = fillAndSubmit(true, ['한빛대학교', '서울대'])
    expect(await screen.findByText('서류에 학교 이름으로 보이는 말이 있어요')).toBeInTheDocument()
    expect(screen.getByText('"한빛대학교", "서울대"')).toBeInTheDocument()
    expect(requests).toEqual(['/api/public/postings/posting-1/applications/school-check'])

    fireEvent.click(screen.getByRole('button', { name: '그대로 제출' }))
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(requests.at(-1)).toBe('/api/public/postings/posting-1/applications')
  })

  it('다시 올리기를 고르면 제출하지 않는다', async () => {
    const { requests, onSubmitted } = fillAndSubmit(true, ['한빛대학교'])
    fireEvent.click(await screen.findByRole('button', { name: '다시 올리기' }))
    await waitFor(() =>
      expect(screen.queryByText('서류에 학교 이름으로 보이는 말이 있어요')).not.toBeInTheDocument(),
    )
    expect(requests).toHaveLength(1)
    expect(onSubmitted).not.toHaveBeenCalled()
  })

  it('학교 이름이 없으면 묻지 않고 제출한다', async () => {
    const blind = fillAndSubmit(true, [])
    await waitFor(() => expect(blind.onSubmitted).toHaveBeenCalled())
    expect(blind.requests).toHaveLength(2)
  })

  it('블라인드가 아니면 학교 이름을 확인하지 않는다', async () => {
    const open = fillAndSubmit(false, ['한빛대학교'])
    await waitFor(() => expect(open.onSubmitted).toHaveBeenCalled())
    expect(open.requests).toEqual(['/api/public/postings/posting-1/applications'])
  })
})
