import { expect, it } from 'vitest'
import { posterPreviewChanges } from './poster-preview'
import { initialPoster, posterTagline } from './poster-design'
import { recolorGeneratedPoster, type PosterCanvas } from './poster-canvas'
import type { PosterPosting } from './PostingPoster'

const posting: PosterPosting = {
  companyName: '우리 회사',
  content: {
    title: '채용',
    jobCategory: '마케팅',
    employmentType: '',
    career: '',
    location: '',
    intro: '',
    duties: [],
    qualifications: [],
    preferred: [],
    benefits: [],
    roles: [],
    headcount: null,
    position: '',
    education: '',
    workHours: '',
    salary: '',
    blind: false,
  },
  stages: [{ name: '2차 면접', type: 'INTERVIEW' }],
  documents: [],
  notices: [],
  openAt: null,
  closeAt: null,
}

it('추가 입력 없이 현재 직무 문구를 쓰고 AI가 제안한 문구는 보존한다', () => {
  expect(posterTagline(posting)).toContain('마케팅')
  expect(
    posterTagline({ ...posting, content: { ...posting.content, jobCategory: '개발' } }),
  ).toContain('개발')
  expect(
    posterTagline(posting, { ...initialPoster(), tagline: '새로운 도전을 함께 시작합니다' }),
  ).toBe('새로운 도전을 함께 시작합니다')
})

it('자동 아이콘의 실제 그림과 비교해 바뀐 전형만 표시한다', () => {
  const before = initialPoster()
  expect(
    posterPreviewChanges(before, { ...before, stageIcons: { '2차 면접': 'USERS' } }, posting)
      .stages,
  ).toEqual([])
  expect(
    posterPreviewChanges(before, { ...before, stageIcons: { '2차 면접': 'MESSAGES' } }, posting),
  ).toEqual({ all: false, stages: ['2차 면접'], bindings: [] })
})

it('생성 대표색은 배너와 본문 강조색·서류 카드·종이색에 함께 반영하고 원본은 보존한다', () => {
  const style = { fontSize: 14, fill: '#101820', fontWeight: 'normal' }
  const doc: PosterCanvas = {
    width: 600,
    height: 900,
    brandColor: '#082858',
    source: { url: 'hiremate:generated', name: '생성', license: 'AI 생성' },
    objects: [
      { hmId: 'generated-header', type: 'Rect', fill: '#082858' },
      { type: 'Textbox', binding: 'title', fill: '#ffffff' },
    ],
    nativeLayout: {
      version: 1,
      paper: '#f7f5ef',
      headerBottom: 300,
      sections: [
        {
          binding: 'documents',
          left: 40,
          top: 400,
          width: 520,
          height: 100,
          heading: style,
          body: style,
          accent: '#b59a58',
          rule: '#b59a58',
          card: '#082858',
          lastCard: '#b59a58',
          cardInk: '#ffffff',
        },
      ],
    },
  }
  const before = JSON.stringify(doc),
    next = recolorGeneratedPoster(doc, '#7c3aed')
  expect(next.objects[0].fill).toBe('#7c3aed')
  expect(next.nativeLayout?.sections[0].card).toBe('#7c3aed')
  expect(next.nativeLayout?.sections[0].rule).not.toBe('#b59a58')
  expect(next.nativeLayout?.paper).not.toBe('#f7f5ef')
  expect(JSON.stringify(doc)).toBe(before)
})
