import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { initialPoster, POSTER_TEMPLATES, posterPalette } from '@/features/posting/poster-design'
import { PostingPoster, type PosterPosting } from '@/features/posting/PostingPoster'

const posting: PosterPosting = {
  companyName: '맑은물',
  content: {
    title: '서비스 운영 담당자',
    jobCategory: '운영',
    employmentType: '정규직',
    career: '경력 2년 이상',
    location: '서울 본사',
    intro: '깨끗한 물을 제공하는 회사입니다.',
    duties: ['정수 서비스 일정 관리'],
    qualifications: ['관련 업무 경험'],
    preferred: ['고객 상담 경험'],
    benefits: ['직무 교육 지원'],
    headcount: 2,
    position: '',
    education: '',
    workHours: '주 5일',
    salary: '협의 후 결정',
  },
  stages: [{ name: '서류 전형' }, { name: '실무 면접' }],
  documents: [{ type: 'RESUME', label: '이력서', format: 'PDF', required: true }],
  notices: ['제출 정보가 사실과 다르면 채용이 취소될 수 있습니다.'],
  openAt: '2026-11-01T00:00:00Z',
  closeAt: '2026-11-15T14:59:00Z',
}

describe('공고 포스터', () => {
  it.each(POSTER_TEMPLATES)(
    '$name에서도 조건과 필수 안내를 생략하거나 꾸며내지 않는다',
    (template) => {
      render(
        <PostingPoster
          posting={posting}
          design={{ ...initialPoster(), enabled: true, template: template.id }}
        />,
      )
      for (const text of [
        '정수 서비스 일정 관리',
        '관련 업무 경험',
        '고객 상담 경험',
        '직무 교육 지원',
        '협의 후 결정',
        '주 5일',
        '이력서 PDF · 필수',
        posting.notices[0],
      ]) {
        expect(screen.getByText(text)).toBeInTheDocument()
      }
      expect(screen.queryByText(/유연한 출퇴근/)).not.toBeInTheDocument()
    },
  )

  it('제출된 문구를 실행 가능한 HTML로 해석하지 않는다', () => {
    const text = '<img src=x onerror=alert(1)>'
    const { container } = render(
      <PostingPoster
        posting={{ ...posting, content: { ...posting.content, intro: text } }}
        design={initialPoster()}
      />,
    )
    expect(screen.getByText(text)).toBeInTheDocument()
    expect(container.querySelector('[onerror]')).toBeNull()
  })

  it('로고 표시를 끄면 파일을 렌더링하지 않는다', () => {
    render(
      <PostingPoster
        posting={posting}
        design={{ ...initialPoster(), logoFileId: 'logo', showLogo: false }}
        logoUrl="/logo.png"
      />,
    )
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('밝은 로고 색상에는 어두운 글자를, 어두운 색상에는 밝은 글자를 적용한다', () => {
    expect(posterPalette('#ffffff')).toHaveProperty('--poster-on-primary', '#17212b')
    expect(posterPalette('#000000')).toHaveProperty('--poster-on-primary', '#ffffff')
    expect(posterPalette('url(evil)')).toHaveProperty('--poster-primary', '#2459a6')
  })
})
