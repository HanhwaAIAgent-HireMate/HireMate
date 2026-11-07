import { describe, expect, it, vi } from 'vitest'
import {
  importPosterTemplate,
  importCanvaPoster,
  importOrshotPoster,
  posterBindings,
  posterCanvasObjects,
  readPosterCanvas,
  sameImportedArtwork,
  samePosterCanvas,
  posterAfterTemplateDeletion,
  nextExternalTemplateName,
  preparePosterLogo,
  clearCanvaLogoPlaceholder,
} from '@/features/posting/poster-canvas'
import type { PosterPosting } from '@/features/posting/PostingPoster'
import { initialPoster, type PosterBrand } from '@/features/posting/poster-design'

const doc = {
  width: 600,
  height: 1000,
  source: { name: '양식', url: 'https://inkscape.de/vorlagen/', license: 'CC0 1.0' },
  objects: [{ type: 'Textbox', hmId: 'title', binding: 'title', left: 40, top: 60, text: '' }],
}

describe('외부 포스터 데이터', () => {
  it.each([
    ['#8b32be', 'PANELS', 'CARDS', 'COMPACT'],
    ['#d85d36', 'EDITORIAL', 'STEPS', 'LIST'],
    ['#082858', 'EDITORIAL', 'TIMELINE', 'TILES'],
  ] as const)(
    'Orshot 원본 %s의 배색을 본문에 잇고 하단 표현을 맞춘다',
    async (color, body, process, documents) => {
      const F = await import('fabric')
      const bitmap = document.createElement('canvas')
      bitmap.width = 600
      bitmap.height = 360
      const context = bitmap.getContext('2d')!
      context.fillStyle = color
      context.fillRect(0, 0, 600, 360)
      const mock = vi.spyOn(F.FabricImage, 'fromURL').mockResolvedValue(new F.FabricImage(bitmap))
      try {
        const imported = readPosterCanvas(
          await importOrshotPoster(
            {
              id: 'orshot:11',
              name: '원본',
              background: bitmap.toDataURL('image/jpeg'),
              width: 600,
              height: 360,
              motionUrl: null,
              motionHeight: 360,
              layoutStyle: null,
            },
            '#082858',
            true,
          ),
        )
        expect(imported.brandColor).toBe(color)
        expect(imported.nativeLayout?.appearance).toMatchObject({ body, process, documents })
        expect(imported.nativeLayout?.sections.every((section) => section.accent === color)).toBe(
          true,
        )
      } finally {
        mock.mockRestore()
      }
    },
  )
  it('Orshot 배경에는 원본 글을 넣지 않고 현재 공고를 채울 편집 영역을 만든다', async () => {
    const F = await import('fabric')
    const bitmap = document.createElement('canvas')
    bitmap.width = 600
    bitmap.height = 360
    const context = bitmap.getContext('2d')!
    context.fillStyle = '#082858'
    context.fillRect(0, 0, 600, 360)
    const mock = vi.spyOn(F.FabricImage, 'fromURL').mockResolvedValue(new F.FabricImage(bitmap))
    try {
      const imported = readPosterCanvas(
        await importOrshotPoster(
          {
            id: 'orshot:11',
            name: '사진형',
            background: bitmap.toDataURL('image/jpeg'),
            width: 600,
            height: 360,
            motionUrl: 'https://storage.orshot.com/test/background.mp4',
            motionHeight: 600,
            layoutStyle: null,
          },
          '#082858',
        ),
      )
      expect(imported.source.id).toBe('orshot:11')
      expect(imported.media?.url).toBe('https://storage.orshot.com/test/background.mp4')
      expect(imported.nativeLayout?.sections.map((section) => section.binding)).toEqual(
        expect.arrayContaining(['intro', 'duties', 'qualifications', 'stages', 'documents']),
      )
      expect(
        imported.objects.filter((object) => object.binding).every((object) => object.text === ''),
      ).toBe(true)
      expect(imported.objects.find((object) => object.binding === 'title')?.fill).toBe('#ffffff')
    } finally {
      mock.mockRestore()
    }
    await expect(
      importOrshotPoster(
        {
          id: 'orshot:11',
          name: '사진형',
          background: 'https://private.example/image.jpg',
          width: 600,
          height: 360,
          motionUrl: null,
          motionHeight: 0,
          layoutStyle: null,
        },
        '#082858',
      ),
    ).rejects.toThrow()
  })
  it('Orshot 출처는 계정 디자인 표기와 유효한 템플릿 번호가 함께 있어야 한다', () => {
    const source = {
      id: 'orshot:36664',
      name: '사진형',
      url: 'https://orshot.com/templates/',
      license: 'Orshot 계정 디자인',
    }
    expect(readPosterCanvas(JSON.stringify({ ...doc, source })).source).toEqual(source)
    for (const invalid of [
      { ...source, id: 'orshot:../private' },
      { ...source, url: 'https://orshot.com.evil.test/templates/' },
      { ...source, license: '무료' },
    ]) {
      expect(() => readPosterCanvas(JSON.stringify({ ...doc, source: invalid }))).toThrow()
    }
  })

  it('선택 중인 템플릿을 삭제하면 저장된 기업 기본 디자인으로 돌아가고 다른 템플릿 삭제는 유지한다', () => {
    const brand: PosterBrand = {
      template: 'PREMIUM',
      mood: 'PREMIUM',
      color: '#79634b',
      decoration: 0,
      logoFileId: null,
      templates: [],
    }
    const canvasJson = JSON.stringify(doc)
    const deleted = {
      id: 'external',
      name: '양식',
      template: 'CLASSIC',
      mood: 'TRUST',
      color: '#082858',
      decoration: 1,
      canvasJson,
    }
    const current = {
      ...initialPoster(),
      canvasJson,
      enabled: true,
      logoFileId: 'saved-logo',
      showLogo: true,
      stageIcons: { 면접: 'USERS' as const },
    }
    const restored = posterAfterTemplateDeletion(current, deleted, brand)
    expect(restored).toMatchObject({
      template: 'PREMIUM',
      color: '#79634b',
      decoration: 0,
      canvasJson: null,
      logoFileId: 'saved-logo',
      showLogo: true,
      stageIcons: current.stageIcons,
    })
    expect(posterAfterTemplateDeletion(restored, deleted, brand)).toBe(restored)
    const custom = { ...deleted, canvasJson: null }
    expect(
      posterAfterTemplateDeletion(
        { ...current, canvasJson: null, color: custom.color },
        custom,
        brand,
      ),
    ).toMatchObject({ template: 'PREMIUM', canvasJson: null })
  })
  it('상단 오른쪽의 빈 로고 테두리만 지우고 다른 장식은 보존한다', () => {
    const canvas = document.createElement('canvas')
    canvas.width = 600
    canvas.height = 850
    const context = canvas.getContext('2d')!
    context.fillStyle = '#00243e'
    context.fillRect(0, 0, 600, 850)
    context.strokeStyle = '#71849c'
    context.lineWidth = 2
    context.strokeRect(462, 28, 104, 66)
    context.fillStyle = '#156fa0'
    context.fillRect(40, 70, 25, 3)
    expect(clearCanvaLogoPlaceholder(canvas)).toBe(true)
    expect([...context.getImageData(462, 40, 1, 1).data]).toEqual([0, 36, 62, 255])
    expect([...context.getImageData(45, 71, 1, 1).data]).toEqual([21, 111, 160, 255])
    expect(clearCanvaLogoPlaceholder(canvas)).toBe(false)
    context.fillStyle = '#71849c'
    context.fillRect(565, 40, 2, 50)
    expect(clearCanvaLogoPlaceholder(canvas)).toBe(true)
    expect([...context.getImageData(565, 60, 1, 1).data]).toEqual([0, 36, 62, 255])
  })
  it('글자와 심벌 윤곽은 보존하고 흰 로고 바탕만 연한 대표색으로 맞춘다', () => {
    const canvas = document.createElement('canvas')
    canvas.width = 30
    canvas.height = 12
    const context = canvas.getContext('2d')!
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, 30, 12)
    context.fillStyle = '#002855'
    context.fillRect(3, 3, 5, 6)
    context.fillStyle = '#ffffff'
    context.fillRect(4, 4, 2, 2)
    context.fillStyle = '#002855'
    context.fillRect(12, 4, 5, 3)
    const result = preparePosterLogo(canvas, '#082858')
    const pixels = result.getContext('2d')!
    expect(result.width).toBe(16)
    expect(result.height).toBe(8)
    expect([...pixels.getImageData(0, 0, 1, 1).data]).toEqual([235, 238, 242, 255])
    expect([...pixels.getImageData(1, 1, 1, 1).data]).toEqual([0, 40, 85, 255])
    expect([...pixels.getImageData(11, 3, 1, 1).data]).toEqual([0, 40, 85, 255])
  })
  it('추가된 외부 템플릿은 충돌하지 않는 순번으로 이름을 붙인다', () => {
    expect(nextExternalTemplateName([])).toBe('외부템플릿1')
    expect(nextExternalTemplateName(['기본형', '외부템플릿1', '외부템플릿3'])).toBe('외부템플릿2')
  })
  it('Canva의 원본 문구와 만료 URL 대신 배경과 현재 공고 연결만 저장한다', async () => {
    const previousFonts = document.fonts
    Object.defineProperty(document, 'fonts', {
      configurable: true,
      value: { ready: Promise.resolve() },
    })
    try {
      const bitmap = document.createElement('canvas')
      bitmap.width = 2
      bitmap.height = 2
      // jsdom의 Image는 data URL을 로드하지 않아 이 경계만 실제 canvas 이미지로 대체한다.
      const F = await import('fabric')
      vi.spyOn(F.FabricImage, 'fromURL').mockResolvedValue(new F.FabricImage(bitmap))
      const posting: PosterPosting = {
        companyName: '우리 회사',
        openAt: null,
        closeAt: null,
        stages: [],
        documents: [],
        notices: [],
        content: {
          title: '마케팅 채용',
          jobCategory: '마케팅',
          employmentType: '정규직',
          career: '신입',
          location: '서울',
          intro: '회사 소개',
          duties: ['캠페인 운영'],
          qualifications: ['관련 지식'],
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
      }
      const encoded = await importCanvaPoster(
        {
          template: {
            id: 'DA123456',
            name: '금융 채용형',
            editUrl: 'https://www.canva.com/d/private-link',
            background: bitmap.toDataURL('image/jpeg'),
            width: 794,
            height: 1123,
            regions: [
              {
                id: 'source-title',
                text: '다른 회사 기밀 문구',
                left: 40,
                top: 80,
                width: 600,
                height: 100,
              },
              { id: 'duties', text: '원본 주요 업무', left: 40, top: 360, width: 300, height: 140 },
              {
                id: 'qualifications',
                text: '원본 자격 요건',
                left: 420,
                top: 360,
                width: 300,
                height: 140,
              },
            ],
          },
          mapping: {
            bindings: [
              { elementId: 'source-title', binding: 'title' },
              { elementId: 'duties', binding: 'duties' },
              { elementId: 'qualifications', binding: 'qualifications' },
            ],
          },
        },
        posting,
        '#082858',
      )
      const imported = readPosterCanvas(encoded)
      expect(imported.source.id).toBe('canva:DA123456')
      expect(imported.objects.some((item) => item.hmId === 'canva-header')).toBe(true)
      expect(imported.canvaLayout?.version).toBe(2)
      expect(
        imported.objects.filter((item) => item.binding).every((item) => item.text === ''),
      ).toBe(true)
      expect(encoded).not.toContain('다른 회사 기밀 문구')
      expect(encoded).not.toContain('private-link')
      expect(
        posterCanvasObjects(imported, posterBindings(posting), '#082858').find(
          (item) => item.binding === 'title',
        ),
      ).toHaveProperty('text', '마케팅 채용')
    } finally {
      vi.restoreAllMocks()
      Object.defineProperty(document, 'fonts', { configurable: true, value: previousFonts })
    }
  })
  it('AI 수정으로 배경과 글자색이 같아져도 상단과 본문을 읽을 수 있게 렌더링한다', () => {
    const input = {
      ...doc,
      brandColor: '#082858',
      objects: [
        { type: 'rect', left: 0, top: 0, width: 600, height: 260, fill: '#082858' },
        { ...doc.objects[0], width: 500, fontSize: 48, fill: '#082858' },
        { ...doc.objects[0], binding: 'benefits', top: 300, width: 500, fill: '#ffffff' },
      ],
    }
    const result = posterCanvasObjects(input, { title: '채용', benefits: '복지 안내' }, '#082858')
    expect(result[1]).toMatchObject({ fill: '#ffffff', fontSize: 48, text: '채용' })
    expect(result[2]).toMatchObject({ fill: '#24313e', text: '복지 안내' })
    expect(result[0]).toEqual(input.objects[0])
    expect(input.objects[1].fill).toBe('#082858')
  })
  it('요소별 편집과 출처를 보존한다', () => {
    expect(readPosterCanvas(JSON.stringify(doc))).toEqual(doc)
  })
  it('이름과 원본 ID가 다른 동일 디자인의 복사본을 구분한다', () => {
    const copy = { ...doc, source: { ...doc.source, id: 'copy', name: '외부템플릿2' } }
    expect(sameImportedArtwork(JSON.stringify(doc), JSON.stringify(copy))).toBe(true)
    expect(sameImportedArtwork(JSON.stringify(doc), JSON.stringify({ ...copy, objects: [] }))).toBe(
      false,
    )
  })
  it('초기 중앙 원점 데이터를 복구하고 최신 색상과 내용만 채운다', () => {
    const old = {
      ...doc,
      brandColor: '#112233',
      objects: [
        { ...doc.objects[0], originX: 'center', originY: 'center', width: 900, fill: '#112233' },
      ],
    }
    const [title] = posterCanvasObjects(old, { title: '현재 공고 제목' }, '#2255aa')
    expect(title).toMatchObject({
      originX: 'left',
      originY: 'top',
      width: 536,
      fill: '#2255aa',
      text: '현재 공고 제목',
      splitByGrapheme: true,
    })
    expect(samePosterCanvas(JSON.stringify(old), JSON.stringify({ ...old, objects: [] }))).toBe(
      true,
    )
    expect(samePosterCanvas('invalid', JSON.stringify(doc))).toBe(false)
  })
  it.each([
    { ...doc, width: 100000 },
    { ...doc, source: { ...doc.source, url: 'javascript:attack()' } },
    { ...doc, objects: [{ type: 'Image', src: 'http://localhost/private' }] },
    { ...doc, objects: [{ type: 'Rect', filters: [{ type: 'malicious' }] }] },
    { ...doc, objects: Array.from({ length: 151 }, () => ({ type: 'Rect' })) },
  ])('지원하지 않는 실행·외부 참조·과도한 요소는 거절한다', (input) => {
    expect(() => readPosterCanvas(JSON.stringify(input))).toThrow()
  })
  it.each(['inkscape-frame', 'inkscape-a4', 'inkscape-a5'])(
    '%s에 긴 공고를 채워도 모든 본문이 포스터 안에 들어간다',
    async (id) => {
      const posting: PosterPosting = {
        companyName: '은행',
        openAt: null,
        closeAt: null,
        content: {
          title: '마케팅 채용',
          jobCategory: '마케팅',
          employmentType: '정규직',
          career: '신입',
          location: '서울',
          intro: '회사 소개',
          duties: ['캠페인 운영', 'API개발과협업과유지보수를안전하게수행하는역량'.repeat(35)],
          qualifications: ['관련 지식'],
          preferred: [],
          benefits: ['교육 지원'],
          roles: [],
          headcount: null,
          position: '',
          education: '',
          workHours: '',
          salary: '',
          blind: false,
        },
        stages: [{ name: '서류 전형' }, { name: '최종면접' }],
        documents: [],
        notices: ['필수 안내'],
      }
      const values = posterBindings(posting)
      expect(values.title).toBe('마케팅 채용')
      expect(values.qualifications).toContain('관련 지식')
      expect(values.notices).toContain('필수 안내')
      expect(values.stages).toBe('전형 절차\n서류 전형 → 최종면접 → 최종 합격')
      expect(
        posterBindings({ ...posting, content: { ...posting.content, title: '인사 채용' } }).title,
      ).toBe('인사 채용')
      const previousFonts = document.fonts
      Object.defineProperty(document, 'fonts', {
        configurable: true,
        value: { ready: Promise.resolve() },
      })
      try {
        const raw = await importPosterTemplate(
          {
            id,
            name: '프레임형',
            sourceUrl: 'https://inkscape.de/vorlagen/',
            license: 'CC0 1.0',
            thumbnailUrl: null,
            svg: '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="850"><rect width="600" height="850" fill="#ffffff"/><text x="30" y="40">다른 회사 원본 문구</text></svg>',
          },
          posting,
          '#112233',
        )
        const canvas = readPosterCanvas(raw)
        expect(canvas.objects.find((item) => item.binding === 'title')).toHaveProperty('text', '')
        expect(raw).not.toContain('다른 회사 원본 문구')
        expect(canvas.objects.some((item) => item.hmId === 'decoration-0')).toBe(true)
        const F = await import('fabric')
        const rendered = new F.StaticCanvas(document.createElement('canvas'), {
          width: canvas.width,
          height: canvas.height,
        })
        try {
          await rendered.loadFromJSON({
            objects: posterCanvasObjects(canvas, values, '#112233'),
          })
          for (const [index, node] of rendered.getObjects().entries()) {
            if (!canvas.objects[index].binding) continue
            const bounds = node.getBoundingRect()
            expect(bounds.left).toBeGreaterThanOrEqual(24)
            expect(bounds.left + bounds.width).toBeLessThanOrEqual(canvas.width - 23)
            expect(bounds.top).toBeGreaterThanOrEqual(24)
            expect(bounds.top + bounds.height).toBeLessThanOrEqual(canvas.height - 23)
          }
          const svg = rendered.toSVG()
          expect(svg).toContain('마케팅 채용')
          expect(svg).toContain('최종 합격')
          expect(svg).not.toContain('다른 회사 원본 문구')
        } finally {
          await rendered.dispose()
        }
      } finally {
        Object.defineProperty(document, 'fonts', { configurable: true, value: previousFonts })
      }
    },
  )
})
