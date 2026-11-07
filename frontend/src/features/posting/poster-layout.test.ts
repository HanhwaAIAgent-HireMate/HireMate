import { expect, it } from 'vitest'
import { importNativePoster, layoutNativePoster } from './poster-layout'
import {
  posterBindings,
  posterCanvasObjects,
  readPosterCanvas,
  type PosterCanvas,
} from './poster-canvas'
import type { PosterPosting } from './PostingPoster'
import { initialPoster } from './poster-design'

it('세로 Orshot 원본의 비율을 유지하며 채용 제목과 본문 사이 높이를 줄인다', async () => {
  const F = await import('fabric')
  const target = new F.StaticCanvas(document.createElement('canvas'), { width: 600, height: 1800 })
  try {
    const image = document.createElement('canvas')
    image.width = 600
    image.height = 1067
    const cover = new F.FabricImage(image, { hmId: 'canva-header' })
    target.add(cover)
    const posting: PosterPosting = {
      companyName: '가온금융',
      openAt: null,
      closeAt: null,
      content: {
        title: 'AX 개발자',
        intro: '디지털 금융을 만듭니다.',
        jobCategory: '개발',
        employmentType: '정규직',
        career: '신입',
        location: '서울',
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
      stages: [],
      documents: [],
      notices: [],
    }
    const style = { fontSize: 14, fill: '#101820', fontWeight: 'normal' }
    const doc: PosterCanvas = {
      width: 600,
      height: 1800,
      originalRender: true,
      source: {
        id: 'orshot:11',
        name: '채용 영상',
        url: 'https://orshot.com/templates/',
        license: '',
      },
      objects: [],
      nativeLayout: {
        version: 1,
        paper: '#ffffff',
        headerBottom: 1067,
        sections: [
          {
            binding: 'intro',
            left: 40,
            top: 1107,
            width: 520,
            height: 100,
            heading: style,
            body: style,
            accent: '#082858',
            rule: '#dce4ef',
            card: '#f2f6fb',
            lastCard: '#082858',
            cardInk: '#ffffff',
          },
        ],
      },
    }
    await layoutNativePoster(target, doc, posting)
    const divider = target.getObjects().find((node) => node.get('hmId') === 'orshot-cover-end')!
    const title = target.getObjects().find((node) => node.get('hmId') === 'title')!
    expect(cover.scaleX).toBe(cover.scaleY)
    expect(divider.top).toBeLessThan(500)
    expect(title.left + title.getScaledWidth()).toBeLessThan(cover.left)
    expect(
      target
        .getObjects()
        .some(
          (node) =>
            node instanceof F.Textbox &&
            node.text.includes('디지털 금융을 만듭니다.') &&
            node.top > divider.top,
        ),
    ).toBe(true)
  } finally {
    await target.dispose()
  }
})

it.each([
  { edition: 3, body: 'EDITORIAL' as const },
  { edition: 3, body: 'PANELS' as const },
  { edition: 3, body: 'SIDEBAR' as const },
  { edition: 4, body: 'EDITORIAL' as const },
])(
  '$body 생성 포스터는 두 단의 빈 공간을 줄이고 모든 항목을 유지한다',
  async ({ edition, body }) => {
    const F = await import('fabric')
    const posting: PosterPosting = {
      companyName: '가온금융',
      openAt: null,
      closeAt: null,
      content: {
        title: '서비스 기획자 채용',
        jobCategory: '서비스 기획',
        employmentType: '정규직',
        career: '신입',
        location: '서울',
        intro: '고객의 일상을 더 편리하게 만드는 금융 서비스를 함께 만듭니다.'.repeat(4),
        duties: ['디지털 서비스 기획 및 운영', '사용자 경험 개선과 데이터 분석'],
        qualifications: ['문제를 논리적으로 정의하는 역량', '명확한 소통과 협업 역량'],
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
      stages: [],
      documents: [],
      notices: [],
    }
    if (edition >= 3) {
      posting.content.qualifications = Array.from(
        { length: 10 },
        (_, index) => `${index + 1}. 고객의 요구를 분석하고 서비스 흐름을 체계적으로 설계하는 역량`,
      )
      posting.content.preferred = ['금융 서비스 운영 경험', '데이터 분석 경험']
      posting.content.benefits = ['유연근무제', '도서 구입비 지원', '건강검진 지원']
    }
    const style = { fontSize: 9, fill: '#ffffff', fontWeight: 'normal' }
    const doc: PosterCanvas = {
      width: 600,
      height: 1200,
      source: {
        id: 'generated:readability',
        name: '생성 양식',
        url: 'hiremate:generated',
        license: '테스트',
      },
      nativeLayout: {
        version: 1,
        paper: '#ffffff',
        headerBottom: 220,
        appearance: { body, process: 'TIMELINE', documents: 'LIST', edition },
        sections: (edition >= 3
          ? ['intro', 'duties', 'qualifications', 'preferred', 'benefits']
          : ['intro', 'duties', 'qualifications']
        ).map((binding, index) => ({
          binding,
          ...(edition === 4
            ? { variant: index === 2 ? ('CHECKLIST' as const) : ('TILE' as const) }
            : {}),
          left: index === 2 ? 312 : 40,
          width: 248,
          top: index ? 500 : 260,
          height: 120,
          heading: { ...style, fontSize: 14 },
          body: style,
          accent: '#2459a6',
          rule: '#c9d7ed',
          card: '#e8eff8',
          lastCard: '#2459a6',
          cardInk: '#24313e',
        })),
      },
      objects: [],
    }
    const target = new F.StaticCanvas(document.createElement('canvas'), {
      width: 600,
      height: 1200,
    })
    try {
      const image = document.createElement('canvas')
      image.width = 1536
      image.height = 1024
      const banner = new F.FabricImage(image, {
        hmId: 'generated-banner',
        left: 300,
        width: 900,
        cropX: 636,
        scaleX: 0.31,
        scaleY: 0.31,
        opacity: 0.32,
      })
      target.add(banner)
      const color = body === 'EDITORIAL' ? '#ec407a' : body === 'PANELS' ? '#2459a6' : '#116644'
      await layoutNativePoster(target, doc, posting, { ...initialPoster(), color })
      expect(banner.cropX).toBe(0)
      expect(banner.opacity).toBe(1)
      expect(banner.scaleX).toBe(banner.scaleY)
      expect(banner.getScaledWidth()).toBeGreaterThanOrEqual(600)
      expect(banner.clipPath?.width).toBe(600)
      expect(
        target.getObjects().some((node) => node.get('hmId') === 'generated-banner-shade'),
      ).toBe(true)
      const shade = target
        .getObjects()
        .find((node) => node.get('hmId') === 'generated-banner-shade')!
      expect(shade.fill).toBeInstanceOf(F.Gradient)
      const gradient = shade.fill as InstanceType<typeof F.Gradient>
      const rgb = [1, 3, 5].map((at) =>
        Math.round(Number.parseInt(color.slice(at, at + 2), 16) * 0.55),
      )
      expect(gradient.colorStops[0].color).toBe(`rgba(${rgb.join(',')},0.96)`)
      const bodies = target
        .getObjects()
        .filter((node) => node instanceof F.Textbox && node.get('hmId'))
      const intro = bodies.find((node) => node.get('hmId') === 'intro')!
      expect(intro.width).toBeGreaterThan(edition === 4 ? 100 : 300)
      if (edition === 4) {
        const backgrounds = target
          .getObjects()
          .filter((node) => node instanceof F.Rect && node.top >= 220)
        expect(backgrounds.every((node) => node.width <= 520)).toBe(true)
      }
      for (const node of bodies) {
        expect(node.width).toBeGreaterThan(100)
        expect(node.get('fontSize')).toBeGreaterThanOrEqual(13)
        expect(node.get('fill')).not.toBe('#ffffff')
        const box = node.getBoundingRect()
        expect(box.left + box.width).toBeLessThanOrEqual(601)
        expect(box.top + box.height).toBeLessThanOrEqual(target.height)
      }
      const duties = bodies.find((node) => node.get('hmId') === 'duties')!
      const qualifications = bodies.find((node) => node.get('hmId') === 'qualifications')!
      expect(duties.top).toBe(qualifications.top)
      expect(duties.left + duties.width).toBeLessThanOrEqual(qualifications.left)
      const visible = bodies.map((node) => String(node.get('text'))).join('\n')
      for (const item of posting.content.qualifications) expect(visible).toContain(item)
      if (edition === 3) {
        const preferred = bodies.find((node) => node.get('hmId') === 'preferred')!
        const qualificationBottom = Math.max(
          ...bodies
            .filter((node) => node.get('hmId') === 'qualifications')
            .map((node) => node.top + node.height),
        )
        expect(preferred.left).toBe(duties.left)
        expect(preferred.top).toBeLessThan(qualificationBottom)
        for (let i = 0; i < bodies.length; i++)
          for (let j = i + 1; j < bodies.length; j++) {
            const a = bodies[i].getBoundingRect(),
              b = bodies[j].getBoundingRect()
            expect(
              a.left + a.width <= b.left ||
                b.left + b.width <= a.left ||
                a.top + a.height <= b.top ||
                b.top + b.height <= a.top,
            ).toBe(true)
          }
      }
    } finally {
      await target.dispose()
    }
  },
)

it('제공처의 100% 도형을 원본 레이어 치수로 보존해 헤더와 로고 장식이 글자를 덮지 않는다', async () => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="1000" data-body-top="250">
    <g data-layer="header" data-kind="SHAPE" data-x="0" data-y="0" data-width="600" data-height="250"><rect width="100%" height="100%" fill="#082858"/></g>
    <g data-layer="mark" data-kind="SHAPE" data-x="30" data-y="30" data-width="12" data-height="12"><g transform="translate(30 30)"><rect width="100%" height="100%" fill="#c2a15f"/></g></g>
    <g data-layer="company" data-kind="TEXT" data-x="50" data-y="30" data-width="200" data-height="30"><text x="50" y="50" fill="#fff" font-size="20">회사</text></g>
    <g data-layer="title" data-kind="TEXT" data-x="30" data-y="100" data-width="500" data-height="80"><text x="30" y="150" fill="#fff" font-size="40">채용</text></g>
    <g data-layer="intro" data-kind="TEXT" data-x="30" data-y="300" data-width="250" data-height="80"><text x="30" y="320">회사 소개</text></g>
    <g data-layer="duties" data-kind="TEXT" data-x="310" data-y="300" data-width="250" data-height="80"><text x="310" y="320">주요 업무</text></g>
  </svg>`
  const value = await importNativePoster(
    {
      id: 'templated:test',
      name: '원본',
      svg,
      sourceUrl: 'https://templated.io/templates/',
      license: 'Templated 테마',
      thumbnailUrl: null,
    },
    {
      sections: [
        { binding: 'company', elements: [2, 3], heading: 3, body: 3 },
        { binding: 'title', elements: [4], heading: 4, body: 4 },
        { binding: 'intro', elements: [5], heading: 5, body: 5 },
        { binding: 'duties', elements: [6], heading: 6, body: 6 },
      ],
    },
    '#082858',
  )
  const doc = readPosterCanvas(value)
  const background = doc.objects.find((node) => node.hmId === 'native-1')!
  const mark = doc.objects.find((node) => node.hmId === 'native-2')!
  expect(Number(background.width) * Number(background.scaleX)).toBe(600)
  expect(Number(background.height) * Number(background.scaleY)).toBe(250)
  expect(Number(mark.width) * Number(mark.scaleX)).toBe(12)
})

it.each([
  { edition: 1, wordTitle: false },
  { edition: 1, wordTitle: true },
  { edition: 3, wordTitle: false },
  { edition: 3, wordTitle: true },
])(
  '버전 $edition의 긴 본문과 제목 어절(검사: $wordTitle)을 보존한다',
  async ({ edition, wordTitle }) => {
    const F = await import('fabric')
    const content = '긴문장과채용조건을생략하거나잘라내지않고유지합니다'.repeat(18)
    const posting: PosterPosting = {
      companyName: '정말긴이름을사용하는테스트기업',
      openAt: '2026-11-01T00:00:00',
      closeAt: '2026-12-01T00:00:00',
      content: {
        title: wordTitle
          ? edition === 1
            ? '프론트엔드 개발자'
            : '품질 관리 담당자 채용'
          : '여러줄로표시해야하는매우긴마케팅채용공고제목입니다'.repeat(3),
        jobCategory: '마케팅',
        employmentType: '정규직',
        career: '신입',
        location: '서울',
        intro: content,
        duties: [content, content],
        qualifications: [content],
        preferred: [content],
        benefits: [content],
        roles: [],
        headcount: 3,
        position: '사원',
        education: '무관',
        workHours: '주 5일',
        salary: '협의',
        blind: false,
      },
      stages: ['서류', '1차 면접', '최종 면접', '추가 평가'].map((name) => ({ name })),
      documents: [
        { type: 'RESUME', label: '이력서', format: 'PDF', required: true },
        {
          type: 'CERTIFICATE',
          label: '매우긴이름의추가첨부문서'.repeat(5),
          format: 'PDF',
          required: false,
        },
      ],
      notices: [content],
    }
    const style = { fontSize: 14, fill: '#101820', fontWeight: 'normal' }
    const bindings = [
      'intro',
      'conditions',
      'duties',
      'qualifications',
      'preferred',
      'benefits',
      'period',
      'notices',
      'stages',
      'documents',
    ]
    const canvas: PosterCanvas = {
      width: 600,
      height: 1600,
      brandColor: '#082858',
      source: {
        id: edition === 1 ? 'templated:test' : 'generated:00000000-0000-0000-0000-000000000001',
        name: '생성 디자인',
        url: edition === 1 ? 'https://templated.io/templates/' : 'hiremate:generated',
        license: edition === 1 ? 'Templated 테마' : 'AI 생성',
      },
      nativeLayout: {
        version: 1,
        paper: '#f7f5ef',
        headerBottom: 300,
        appearance: { body: 'EDITORIAL', process: 'CARDS', documents: 'TILES', edition },
        sections: bindings.map((binding, index) => ({
          binding,
          left: index % 2 ? 310 : 40,
          top: 340 + Math.floor(index / 2) * 180,
          width: 250,
          height: 120,
          heading: { ...style, fontSize: 18, fontWeight: 'bold' },
          body: style,
          accent: '#082858',
          rule: '#b59a58',
          card: '#082858',
          lastCard: '#b59a58',
          cardInk: '#ffffff',
        })),
      },
      objects: [
        {
          type: 'Rect',
          hmId: 'generated-header',
          left: 0,
          top: edition === 3 ? 16 : 0,
          width: 600,
          height: 300,
          fill: '#082858',
          originX: 'left',
          originY: 'top',
        },
        ...['company', 'title', 'tags'].map((binding, index) => ({
          type: 'Textbox',
          hmId: binding,
          binding,
          text: '',
          left: 40,
          top: 30 + index * 85,
          width: index === 0 ? 300 : index === 1 && wordTitle ? 320 : 440,
          fontSize: index === 1 ? (edition === 1 ? 80 : 48) : 14,
          fill: '#ffffff',
          originX: 'left',
          originY: 'top',
          splitByGrapheme: true,
        })),
      ],
    }
    const saved = JSON.stringify(canvas)
    expect(saved).not.toContain(posting.companyName)
    const doc = readPosterCanvas(saved)
    const target = new F.StaticCanvas(document.createElement('canvas'), {
      width: doc.width,
      height: doc.height,
    })
    try {
      await target.loadFromJSON({
        objects: posterCanvasObjects(doc, posterBindings(posting), '#082858'),
      })
      await layoutNativePoster(target, doc, posting)
      const text = target
        .getObjects()
        .filter((node): node is InstanceType<typeof F.Textbox> => node instanceof F.Textbox)
      const all = text.map((node) => node.text).join('\n')
      for (const value of [
        content,
        posting.companyName,
        posting.content.title,
        '최종 합격',
        '추가 평가',
        '이력서',
        '모집 조건',
      ])
        expect(all).toContain(value)
      expect(target.height).toBeGreaterThan(1600)
      if (wordTitle && edition === 1) {
        const title = target.getObjects().find((node) => node.get('hmId') === 'title')!
        const lines = (title as InstanceType<typeof F.Textbox>).textLines
        expect(lines.join(' ')).toContain('개발자')
        expect(lines).not.toContain('자')
        expect(title.get('fontSize')).toBeLessThanOrEqual(56)
      }
      if (edition === 3) {
        const background = target
          .getObjects()
          .find((node) => node.get('hmId') === 'generated-header')!
        const title = target.getObjects().find((node) => node.get('hmId') === 'title')!
        expect(title).toBeInstanceOf(F.Textbox)
        const lines = (title as InstanceType<typeof F.Textbox>).textLines
        expect(lines.length).toBeGreaterThan(1)
        if (wordTitle) {
          expect(lines.some((line) => line.includes('채용'))).toBe(true)
          expect(lines).not.toContain('용')
        } else expect(title.get('splitByGrapheme')).toBe(true)
        expect(background.top + background.getScaledHeight()).toBeGreaterThan(
          title.top + title.getScaledHeight(),
        )
      }
      for (const node of text) {
        const bounds = node.getBoundingRect()
        expect(bounds.left).toBeGreaterThanOrEqual(0)
        expect(bounds.left + bounds.width).toBeLessThanOrEqual(601)
        expect(bounds.top + bounds.height).toBeLessThanOrEqual(target.height)
      }
      for (let i = 0; i < text.length; i++)
        for (let j = i + 1; j < text.length; j++) {
          const a = text[i].getBoundingRect(),
            b = text[j].getBoundingRect()
          expect(
            a.left + a.width <= b.left ||
              b.left + b.width <= a.left ||
              a.top + a.height <= b.top ||
              b.top + b.height <= a.top,
            `${text[i].text.slice(0, 12)} / ${text[j].text.slice(0, 12)}`,
          ).toBe(true)
        }
    } finally {
      await target.dispose()
    }
  },
)
