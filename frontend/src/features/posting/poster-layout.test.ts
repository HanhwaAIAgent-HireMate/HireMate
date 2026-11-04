import { expect, it } from 'vitest'
import { importNativePoster, layoutNativePoster } from './poster-layout'
import {
  posterBindings,
  posterCanvasObjects,
  readPosterCanvas,
  type PosterCanvas,
} from './poster-canvas'
import type { PosterPosting } from './PostingPoster'

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

it('생성한 템플릿에 긴 공고를 채우고 겹침 없이 늘리며 저장 데이터에 채용 사실을 굽지 않는다', async () => {
  const F = await import('fabric')
  const content = '긴문장과채용조건을생략하거나잘라내지않고유지합니다'.repeat(18)
  const posting: PosterPosting = {
    companyName: '정말긴이름을사용하는테스트기업',
    openAt: '2026-11-01T00:00:00',
    closeAt: '2026-12-01T00:00:00',
    content: {
      title: '여러줄로표시해야하는매우긴마케팅채용공고제목입니다'.repeat(3),
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
      id: 'generated:00000000-0000-0000-0000-000000000001',
      name: '생성 디자인',
      url: 'hiremate:generated',
      license: 'AI 생성',
    },
    nativeLayout: {
      version: 1,
      paper: '#f7f5ef',
      headerBottom: 300,
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
        left: 0,
        top: 0,
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
        width: index === 0 ? 300 : 440,
        fontSize: index === 1 ? 48 : 14,
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
})
