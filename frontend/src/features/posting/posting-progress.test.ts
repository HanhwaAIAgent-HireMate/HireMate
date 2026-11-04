import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { lastPostingStep, rememberPostingStep } from './posting-progress'
import { currentPath, type RecruitmentCard } from '@/features/dashboard/api'

const member = { companyId: 'company-1', memberId: 'member-1' }
const base = '/hr/recruitments/draft-1/posting'
beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

it('공고마다 마지막 방문 단계를 기억하고 이전으로 돌아간 위치도 갱신한다', () => {
  rememberPostingStep(member, `${base}/poster`)
  rememberPostingStep(member, '/hr')
  expect(lastPostingStep(member, 'draft-1')).toBe('poster')
  rememberPostingStep(member, '/hr/recruitments/another/posting/publish')
  expect(lastPostingStep(member, 'draft-1')).toBe('poster')
  expect(lastPostingStep(member, 'another')).toBe('publish')
  rememberPostingStep(member, base)
  expect(lastPostingStep(member, 'draft-1')).toBe('content')
  rememberPostingStep(member, `${base}/status`)
  expect(lastPostingStep(member, 'draft-1')).toBeUndefined()
})

it('다른 계정·기업의 편집 위치를 사용하지 않고 허용한 단계만 읽는다', () => {
  rememberPostingStep(member, `${base}/publish`)
  expect(lastPostingStep({ ...member, memberId: 'member-2' }, 'draft-1')).toBeUndefined()
  expect(lastPostingStep({ ...member, companyId: 'company-2' }, 'draft-1')).toBeUndefined()
  expect(lastPostingStep(null, 'draft-1')).toBeUndefined()
  localStorage.setItem(localStorage.key(0)!, 'https://example.com')
  expect(lastPostingStep(member, 'draft-1')).toBeUndefined()
})

it('저장소를 사용할 수 없으면 기존 공고 작성 경로로 안전하게 돌아간다', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('denied')
  })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('denied')
  })
  expect(() => rememberPostingStep(member, base)).not.toThrow()
  expect(lastPostingStep(member, 'draft-1')).toBeUndefined()
})

it('작성 중 공고만 이어서 열고 게시·전형 진행 경로에는 영향을 주지 않는다', () => {
  const card: RecruitmentCard = {
    recruitmentId: 'draft-1',
    postingId: 'posting-1',
    title: '채용',
    status: 'DRAFT',
    applicantCount: 0,
    closeAt: null,
    currentStageId: null,
    steps: [],
    createdAt: '2026-11-04T00:00:00Z',
  }
  expect(currentPath(card, 'poster')).toBe(`${base}/poster`)
  expect(currentPath(card, 'publish')).toBe(`${base}/publish`)
  expect(currentPath(card, 'content')).toBe(base)
  expect(currentPath(card)).toBe(base)
  expect(currentPath({ ...card, status: 'PUBLISHED' }, 'poster')).toBe(`${base}/status`)
  expect(
    currentPath({ ...card, status: 'IN_PROGRESS', currentStageId: 'stage-1' }, 'publish'),
  ).toBe('/hr/recruitments/draft-1/stages/stage-1')
})
