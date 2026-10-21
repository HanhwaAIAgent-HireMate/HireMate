import { describe, expect, it } from 'vitest'

import { careerLabel, hasPendingAnalysis } from '@/features/screening/api'

describe('hasPendingAnalysis', () => {
  it('분석 중인 지원자가 있을 때만 다시 불러온다', () => {
    expect(hasPendingAnalysis([{ analysisStatus: 'DONE' }, { analysisStatus: 'PENDING' }])).toBe(
      true,
    )
    expect(hasPendingAnalysis([{ analysisStatus: 'DONE' }, { analysisStatus: 'FAILED' }])).toBe(
      false,
    )
    expect(hasPendingAnalysis([])).toBe(false)
  })
})

describe('careerLabel', () => {
  it('경력을 읽기 전에는 분석 상태를 보여 준다', () => {
    const row = { careerYears: null, lastCompany: null }
    expect(careerLabel({ ...row, analysisStatus: 'PENDING' })).toBe('분석 중')
    expect(careerLabel({ ...row, analysisStatus: 'FAILED' })).toBe('분석 실패')
    expect(careerLabel({ careerYears: 5, lastCompany: 'OO카드', analysisStatus: 'DONE' })).toBe(
      '경력 5년 · OO카드',
    )
  })
})
