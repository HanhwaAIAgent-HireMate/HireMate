import { expect, it } from 'vitest'
import { creativeOrshotLayout } from './poster-creative-layout'
import { ORSHOT_SOURCE_LAYOUTS } from './orshot-source-layouts'
import { layoutOrshotSource } from './poster-source-layout'
import type { NativeLayout } from './poster-layout'
import {
  prepareTemplatedRegistration,
  readPosterCanvas,
  refreshOrshotCanvas,
  type PosterCanvas,
} from './poster-canvas'
import { initialPoster } from './poster-design'
import type { PosterPosting } from './PostingPoster'

const base: NativeLayout = { version: 1, paper: '#ffffff', headerBottom: 500, sections: [] }
const posting: PosterPosting = {
  companyName: '테스트 은행',
  openAt: null,
  closeAt: null,
  content: {
    title: '서비스 기획자 채용',
    jobCategory: '서비스 기획',
    employmentType: '정규직',
    career: '신입',
    location: '서울',
    intro: '고객의 일상을 편리하게 만드는 금융 서비스를 함께 만듭니다.'.repeat(16),
    duties: ['디지털 서비스 기획 및 운영'],
    qualifications: Array.from(
      { length: 12 },
      (_, i) => `${i + 1}. 요구를 분석하고 서비스 흐름을 체계적으로 설계하는 역량`,
    ),
    preferred: ['금융 서비스 운영 경험'],
    benefits: ['유연근무제'],
    roles: [],
    headcount: 2,
    position: '사원',
    education: '무관',
    workHours: '주 5일',
    salary: '협의',
    blind: false,
  },
  stages: Array.from({ length: 5 }, (_, i) => ({
    name: `${i + 1}차 면접`,
    type: 'INTERVIEW' as const,
  })),
  documents: [
    { type: 'RESUME', label: '이력서', format: 'PDF', required: true },
    { type: 'PORTFOLIO', label: '포트폴리오', format: 'PDF', required: false },
  ],
  notices: ['일정은 사전 안내 후 변경될 수 있습니다.'],
}
it('등록용 벡터는 긴 현재 공고를 채우고 늘어난 높이와 편집 원본을 유지한다', async () => {
  const style = { fontSize: 14, fill: '#101820', fontWeight: 'normal' }
  const doc: PosterCanvas = {
    width: 600,
    height: 700,
    brandColor: '#082858',
    templatedRegistration: true,
    source: {
      id: 'generated:00000000-0000-0000-0000-000000000001',
      name: '금융 서비스 채용',
      url: 'hiremate:generated',
      license: 'AI 생성',
    },
    objects: [
      {
        type: 'Textbox',
        binding: 'title',
        hmId: 'title',
        text: '',
        left: 40,
        top: 40,
        width: 520,
        fontSize: 36,
        fill: '#082858',
      },
    ],
    nativeLayout: {
      ...base,
      headerBottom: 150,
      sections: ['intro', 'duties', 'qualifications', 'stages', 'documents'].map(
        (binding, index) => ({
          binding,
          left: 40,
          top: 180 + index * 100,
          width: 520,
          height: 100,
          heading: style,
          body: style,
          accent: '#082858',
          rule: '#eeeeee',
          card: '#082858',
          lastCard: '#c2a15f',
          cardInk: '#ffffff',
        }),
      ),
    },
  }
  const canvasJson = JSON.stringify(doc)
  const request = await prepareTemplatedRegistration(posting, { ...initialPoster(), canvasJson })
  const svg = new DOMParser().parseFromString(request.svg, 'image/svg+xml')
  expect(request.height).toBeGreaterThan(doc.height)
  expect(svg.documentElement.getAttribute('viewBox')).toBe(`0 0 600 ${request.height}`)
  const text = svg.documentElement.textContent.replace(/\s/g, '')
  for (const value of [
    posting.content.title,
    posting.content.intro,
    posting.content.qualifications.at(-1)!,
    '포트폴리오',
    '최종 합격',
  ]) {
    expect(text).toContain(value.replace(/\s/g, ''))
  }
  expect(request.sourceId).toBe(doc.source.id)
  expect(JSON.stringify(doc)).toBe(canvasJson)
})
it.each(Object.keys(ORSHOT_SOURCE_LAYOUTS))(
  '%s 원본 구성은 유지하고 긴 내용만 확장하며 재배치 시 중복하지 않는다',
  async (style) => {
    const F = await import('fabric')
    const layout = creativeOrshotLayout(style, base)
    const source = ORSHOT_SOURCE_LAYOUTS[style]
    expect(layout.sourceTemplate).toBe(style)
    const doc: PosterCanvas = {
      width: 600,
      height: 1700,
      source: { id: 'orshot:test', name: style, url: 'https://orshot.com', license: 'test' },
      nativeLayout: layout,
      objects: [],
    }
    const canvas = new F.StaticCanvas(document.createElement('canvas'), {
      width: 600,
      height: 1700,
    })
    try {
      await layoutOrshotSource(canvas, doc, posting, undefined)
      const count = canvas.getObjects().length
      await layoutOrshotSource(canvas, doc, posting, undefined)
      expect(canvas.getObjects()).toHaveLength(count)
      const texts = canvas.getObjects().filter((node) => node instanceof F.Textbox)
      const visible = texts.map((node) => String(node.get('text'))).join('\n')
      expect(visible).toContain(posting.content.intro)
      for (const line of posting.content.qualifications) expect(visible).toContain(line)
      expect(visible).toContain('최종 합격')
      expect(visible).toContain('이력서 (PDF · 필수)')
      expect(visible).toContain('포트폴리오 (PDF · 선택)')
      for (const node of texts) {
        expect(node.left).toBeGreaterThanOrEqual(0)
        expect(node.left + node.width).toBeLessThanOrEqual(601)
        expect(node.top + node.height).toBeLessThan(canvas.height)
      }
      const preferred = texts.find((n) => n.get('hmId') === 'preferred')!
      const qualification = texts.filter((n) => n.get('hmId') === 'qualifications')
      expect(preferred.top).toBeGreaterThan(Math.max(...qualification.map((n) => n.top + n.height)))
      const final = texts.find((n) => n.get('hmId') === 'stage:최종 합격')!
      expect(final.left).toBe(source.stages.cells[1].shape.left + 10)
      for (const original of source.sections) {
        const heading = texts.find((n) => n.get('text') === original.heading.label)!
        expect(heading.fill).toBe(original.heading.color)
        for (const bar of original.shapes.filter(
          (item) => item.top + item.height <= original.body.top + 1,
        )) {
          const decoration = canvas
            .getObjects()
            .find(
              (node) =>
                node instanceof F.Rect &&
                node.get('hmId') === original.binding &&
                node.left === bar.left &&
                node.width === bar.width &&
                node.fill === bar.fill,
            )!
          expect(decoration.height).toBe(bar.height)
        }
      }
    } finally {
      await canvas.dispose()
    }
  },
)
it('알 수 없는 원본을 다른 유형으로 대체하지 않는다', () => {
  expect(creativeOrshotLayout(null, base)).toBe(base)
  expect(creativeOrshotLayout('UNKNOWN', base)).toBe(base)
})

it('이전 저장본을 갱신할 때도 원본 본문 구성으로 전환하고 HR 수정은 유지한다', () => {
  const saved: PosterCanvas = {
    width: 600,
    height: 1700,
    source: {
      id: 'orshot:37797',
      name: '콜라주',
      url: 'https://orshot.com/templates/',
      license: 'Orshot 계정 디자인',
    },
    nativeLayout: base,
    objects: [
      { type: 'Textbox', hmId: 'intro', binding: 'intro', hmNativeBody: true, fill: '#215641' },
    ],
  }
  const next: PosterCanvas = {
    ...saved,
    nativeLayout: creativeOrshotLayout('COLLAGE', base),
    orshotContentKey: 'new-content',
  }
  const migrated = readPosterCanvas(
    refreshOrshotCanvas(JSON.stringify(saved), JSON.stringify(next)),
  )
  expect(migrated.nativeLayout?.sourceTemplate).toBe('COLLAGE')
  expect(migrated.objects.find((n) => n.hmId === 'intro')?.fill).toBe('#215641')
  expect(migrated.orshotContentKey).toBe('new-content')
  expect(
    readPosterCanvas(refreshOrshotCanvas(JSON.stringify(migrated), JSON.stringify(next))),
  ).toEqual(migrated)
})

it('원본을 저장해 다시 읽어도 제목·본문 스타일 수정과 최신 공고를 반영한다', async () => {
  const F = await import('fabric')
  const source = ORSHOT_SOURCE_LAYOUTS.TYPE
  const doc: PosterCanvas = {
    width: 600,
    height: 1700,
    source: { id: 'orshot:test', name: 'TYPE', url: 'https://orshot.com', license: 'test' },
    nativeLayout: creativeOrshotLayout('TYPE', base),
    objects: [
      {
        hmId: 'intro',
        binding: 'intro',
        hmNativeBody: true,
        type: 'Textbox',
        fontSize: 19,
        fill: '#215641',
        fontWeight: 'bold',
        textAlign: 'center',
      },
    ],
  }
  const first = source.sections[0]
  doc.nativeLayout!.sections.push({
    binding: first.binding,
    left: first.body.left,
    top: first.body.top,
    width: first.body.width,
    height: first.body.height,
    heading: { fontSize: 30, fill: '#123456', fontWeight: 'bold' },
    body: { fontSize: 19, fill: '#215641', fontWeight: 'bold' },
    accent: '#123456',
    rule: '#eeeeee',
    card: '#ffffff',
    lastCard: '#123456',
    cardInk: '#ffffff',
  })
  const canvas = new F.StaticCanvas(document.createElement('canvas'), { width: 600, height: 1700 })
  try {
    const reopened = JSON.parse(JSON.stringify(doc)) as PosterCanvas
    await layoutOrshotSource(canvas, reopened, posting, undefined)
    const heading = canvas
      .getObjects()
      .find((n) => n instanceof F.Textbox && n.get('text') === first.heading.label)!
    const body = canvas
      .getObjects()
      .find((n) => n instanceof F.Textbox && n.get('text') === posting.content.intro)!
    expect(heading.fill).toBe('#123456')
    expect(heading.get('fontSize')).toBe(30)
    expect(body.fill).toBe('#215641')
    expect(body.get('fontSize')).toBe(19)
    expect(body.get('textAlign')).toBe('center')
    expect(body.top).toBeGreaterThan(heading.top + heading.height)
    const updated = {
      ...posting,
      content: { ...posting.content, intro: '수정한 회사 소개', qualifications: ['새 자격 요건'] },
    }
    await layoutOrshotSource(canvas, reopened, updated, undefined)
    const visible = canvas
      .getObjects()
      .filter((n) => n instanceof F.Textbox)
      .map((n) => String(n.get('text')))
      .join('\n')
    expect(visible).toContain('수정한 회사 소개')
    expect(visible).toContain('새 자격 요건')
    expect(visible).not.toContain(posting.content.intro)
  } finally {
    await canvas.dispose()
  }
})
