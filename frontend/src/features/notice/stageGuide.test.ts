import { describe, expect, it } from 'vitest'

import type { StageGuide, StageGuideView } from './api'
import {
  addDays,
  guideProblems,
  isHttpUrl,
  missingGuideFields,
  scheduleBounds,
  scheduleRange,
  todayIso,
} from './stageGuide'

const empty: StageGuide = {
  schedule: null,
  time: null,
  method: null,
  place: '',
  preparation: '',
  note: '',
}

function view(stageId: string, name: string, schedule: string | null): StageGuideView {
  return {
    stageId,
    seq: 0,
    name,
    type: 'ASSESSMENT',
    guide: { ...empty, schedule },
    missing: [],
    notifiedCount: 0,
  }
}

describe('전형별 안내 입력 검사', () => {
  it('오늘과 날짜 계산은 YYYY-MM-DD로 한다', () => {
    expect(todayIso(new Date(2026, 9, 27, 23, 59))).toBe('2026-10-27')
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01')
    expect(addDays('2026-11-01', -1)).toBe('2026-10-31')
  })

  it('일정을 정한 가장 가까운 앞 · 뒤 전형으로 범위를 정한다', () => {
    const views = [
      view('a', '코딩테스트', '2026-11-03'),
      view('b', '1차 면접', null),
      view('c', '2차 면접', null),
      view('d', '임원 면접', '2026-11-20'),
    ]
    const bounds = scheduleBounds(views, 'c')
    expect(bounds).toEqual({
      before: { name: '코딩테스트', date: '2026-11-03' },
      after: { name: '임원 면접', date: '2026-11-20' },
    })
    expect(scheduleRange(bounds, '2026-10-27')).toEqual({ min: '2026-11-04', max: '2026-11-19' })
    expect(scheduleRange({}, '2026-10-27')).toEqual({ min: '2026-10-27', max: undefined })
  })

  it('지난 날짜와 앞 · 뒤 전형과 맞지 않는 날짜는 막는다', () => {
    const bounds = {
      before: { name: '코딩테스트', date: '2026-11-03' },
      after: { name: '임원 면접', date: '2026-11-20' },
    }
    const check = (schedule: string, saved: string | null = null) =>
      guideProblems({ ...empty, schedule }, { ...empty, schedule: saved }, bounds, '2026-10-27')
        .schedule
    expect(check('2026-11-10')).toBeUndefined()
    expect(check('2026-10-01')).toBe('지난 날짜는 고를 수 없어요.')
    expect(check('2026-11-03')).toContain('앞 전형(코딩테스트, 2026-11-03)')
    expect(check('2026-11-20')).toContain('다음 전형(임원 면접, 2026-11-20)')
    expect(check('11월 3일')).toBe('날짜를 다시 골라 주세요.')
    // 이미 지난 전형은 날짜를 바꾸지 않으면 다른 칸을 고칠 수 있다
    expect(
      guideProblems(
        { ...empty, schedule: '2026-10-01', note: '메모' },
        { ...empty, schedule: '2026-10-01' },
        {},
        '2026-10-27',
      ).schedule,
    ).toBeUndefined()
  })

  it('온라인은 http(s) 주소, 오프라인은 장소를 꼭 쓰고, 진행 방식을 고르기 전에는 장소를 쓸 수 없다', () => {
    const place = (method: StageGuide['method'], value: string) =>
      guideProblems({ ...empty, method, place: value }, empty, {}, '2026-10-27').place
    expect(place('ONLINE', 'https://meet.example.com/abc')).toBeUndefined()
    expect(place('ONLINE', '')).toBeUndefined()
    expect(place('ONLINE', 'meet.example.com')).toContain('http://')
    expect(place('OFFLINE', '서울 중구 OO빌딩 5층')).toBeUndefined()
    expect(place('OFFLINE', ' ')).toContain('꼭')
    expect(place(null, '본사')).toContain('진행 방식')
    expect(isHttpUrl('ftp://example.com')).toBe(false)
  })

  it('비어 있는 칸을 알려 준다', () => {
    expect(missingGuideFields(empty)).toEqual(['일정', '진행 방식', '장소·접속 링크', '준비 사항'])
    expect(
      missingGuideFields({
        schedule: '2026-11-03',
        time: null,
        method: 'OFFLINE',
        place: '본사',
        preparation: '신분증',
        note: '',
      }),
    ).toEqual([])
  })
})

describe('오늘로 정한 시작 시각', () => {
  const bounds = { before: undefined, after: undefined }
  it('지난 시간은 고를 수 없고, 바꾸지 않은 시각은 그대로 둘 수 있다', () => {
    const draft = { ...empty, schedule: '2026-11-05', time: '09:00' }
    expect(guideProblems(draft, empty, bounds, '2026-11-05', '10:30').schedule).toBe(
      '지난 시간은 고를 수 없어요.',
    )
    expect(guideProblems(draft, empty, bounds, '2026-11-05', '08:30').schedule).toBeUndefined()
    expect(guideProblems(draft, draft, bounds, '2026-11-05', '10:30').schedule).toBeUndefined()
  })
})
