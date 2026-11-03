import { describe, expect, it } from 'vitest'

import type { PostingContent } from './api'
import {
  careerLevel,
  conditionRows,
  formatCareer,
  parseCareer,
  toCareerYears,
  toHeadcount,
  workRows,
} from './conditions'

const content: PostingContent = {
  roles: [],
  blind: false,
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

describe('경력', () => {
  it('종류와 연차로 나누고 다시 합친다', () => {
    expect(parseCareer('경력 3년 이상')).toEqual({ kind: '경력', years: 3 })
    expect(parseCareer('신입')).toEqual({ kind: '신입', years: null })
    expect(parseCareer('경력 무관')).toEqual({ kind: '경력 무관', years: null })
    expect(parseCareer('3년 차 이상')).toEqual({ kind: null, years: null })
    expect(formatCareer('경력', 5)).toBe('경력 5년 이상')
    expect(formatCareer('경력', null)).toBe('경력')
    expect(formatCareer('신입', 5)).toBe('신입')
  })

  it('연차 칸은 1~99만 받는다', () => {
    expect(toCareerYears('3')).toBe(3)
    expect(toCareerYears('')).toBeNull()
    expect(toCareerYears('0')).toBeNull()
    expect(toCareerYears('100')).toBeNull()
    expect(toCareerYears('2.5')).toBeNull()
  })
})

describe('근무 조건', () => {
  it('근무지 · 근무 요일 · 시간 · 급여 중 채운 칸만 순서대로 보여 준다', () => {
    expect(workRows({ ...content, location: '서울 강남구', workHours: '' })).toEqual([
      { label: '근무지', value: '서울 강남구' },
      { label: '급여', value: '회사 내규에 따름' },
    ])
  })
})

describe('careerLevel', () => {
  it('신입도 지원할 수 있는 경력과 경력직 경력을 나눈다', () => {
    for (const career of ['신입', '경력 무관', '', '신입 · 경력']) {
      expect(careerLevel(career)).toBe('entry')
    }
    for (const career of ['경력', '경력 3년 이상']) {
      expect(careerLevel(career)).toBe('experienced')
    }
  })
})
