import { describe, expect, it } from 'vitest'

import type { PostingContent } from './api'
import { focusLabel, hasLine, toServerFocus } from './focus'

const content: PostingContent = {
  title: '결제 백엔드 개발자',
  jobCategory: '',
  employmentType: '',
  career: '',
  location: '',
  intro: '',
  duties: [],
  qualifications: [],
  preferred: ['금융 도메인 경험', '', '대용량 트래픽 처리 경험'],
  benefits: [],
  headcount: null,
  position: '',
  education: '',
  workHours: '',
  salary: '',
}

describe('줄 골라 AI에게 맡기기', () => {
  it('입력칸 위에는 칸 이름과 화면의 줄 번호를 보여 준다', () => {
    expect(focusLabel({ field: 'preferred', index: 2 })).toBe('우대 사항 3번')
    expect(focusLabel({ field: 'intro' })).toBe('회사 소개')
  })

  it('빈 줄과 없는 줄은 고를 수 없고, 회사 소개는 비어 있어도 고를 수 있다', () => {
    expect(hasLine({ field: 'preferred', index: 0 }, content)).toBe(true)
    expect(hasLine({ field: 'preferred', index: 1 }, content)).toBe(false)
    expect(hasLine({ field: 'preferred', index: 3 }, content)).toBe(false)
    expect(hasLine({ field: 'intro' }, content)).toBe(true)
  })

  it('서버에는 빈 줄을 뺀 순서로 보낸다', () => {
    expect(toServerFocus({ field: 'preferred', index: 2 }, content)).toEqual({
      field: 'preferred',
      index: 1,
    })
    expect(toServerFocus({ field: 'intro' }, content)).toEqual({ field: 'intro', index: null })
  })
})
