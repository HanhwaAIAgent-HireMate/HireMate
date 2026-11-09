import { describe, expect, it } from 'vitest'

import { applicantPhoto, guessGender } from '@/lib/applicant-photo'

describe('지원자 예시 사진', () => {
  it('이름으로 성별을 짐작한다', () => {
    expect(guessGender('박지훈')).toBe('man')
    expect(guessGender('김서연')).toBe('woman')
    expect(guessGender('황보민재')).toBe('man')
  })

  it('블라인드로 가린 이름은 사진을 붙이지 않는다', () => {
    expect(guessGender('12번 지원자')).toBeNull()
    expect(applicantPhoto('a-1', '12번 지원자')).toBeNull()
  })

  it('성별을 짐작하지 못한 이름도 남자 · 여자 사진 가운데 하나를 붙인다', () => {
    expect(guessGender('홍지안')).toBeNull()
    expect(applicantPhoto('application-3', '홍지안')).toMatch(
      /^\/applicants\/(man|woman)_[1-4]\.jpg$/,
    )
  })

  it('같은 지원자는 늘 같은 사진이고, 성별에 맞는 사진만 고른다', () => {
    const photo = applicantPhoto('application-1', '김서연')
    expect(photo).toMatch(/^\/applicants\/woman_[1-4]\.jpg$/)
    expect(applicantPhoto('application-1', '김서연')).toBe(photo)
    expect(applicantPhoto('application-2', '박지훈')).toMatch(/^\/applicants\/man_[1-4]\.jpg$/)
  })
})
