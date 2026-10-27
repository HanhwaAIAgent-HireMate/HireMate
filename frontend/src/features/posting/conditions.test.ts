import { describe, expect, it } from 'vitest'

import type { PostingContent } from './api'
import { conditionRows, toHeadcount } from './conditions'

const content: PostingContent = {
  title: '결제 백엔드 개발자',
  jobCategory: '',
  employmentType: '',
  career: '',
  location: '',
  intro: '',
  duties: [],
  qualifications: [],
  preferred: [],
  benefits: [],
  headcount: 3,
  position: '',
  education: '학력 무관',
  workHours: '',
  salary: '회사 내규에 따름',
}

describe('모집 조건', () => {
  it('채용 인원은 1~9999의 정수만 받는다', () => {
    expect(toHeadcount('3')).toBe(3)
    expect(toHeadcount('')).toBeNull()
    expect(toHeadcount('0')).toBeNull()
    expect(toHeadcount('2.5')).toBeNull()
    expect(toHeadcount('10000')).toBeNull()
  })

  it('지원자 화면에는 채운 칸만 보여 주고 채용 인원에 명을 붙인다', () => {
    expect(conditionRows(content)).toEqual([
      { label: '채용 인원', value: '3명' },
      { label: '학력', value: '학력 무관' },
      { label: '급여', value: '회사 내규에 따름' },
    ])
    expect(conditionRows({ ...content, headcount: null, education: '', salary: '' })).toEqual([])
  })
})
