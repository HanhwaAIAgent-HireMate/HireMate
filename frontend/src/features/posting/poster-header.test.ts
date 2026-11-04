import { expect, it } from 'vitest'
import { layoutCanvaPoster, type PosterCanvas } from './poster-canvas'

it.each([100, 305.6697])(
  '원본 회사명 y=%s도 제목/요약/회사소개와 겹치지 않고 헤더 안에 둔다',
  async (companyTop) => {
    const F = await import('fabric')
    const doc: PosterCanvas = {
      width: 600,
      height: 1000,
      source: {
        name: '오래된 Canva 양식',
        url: 'https://www.canva.com/',
        license: 'Canva 계정 디자인',
      },
      canvaLayout: {
        version: 2,
        headerHeight: 260,
        paper: '#f4f2e3',
        ink: '#24313e',
        accent: '#082858',
        columns: 1,
      },
      objects: [
        {
          type: 'Rect',
          hmId: 'canva-header',
          left: 0,
          top: 0,
          width: 600,
          height: 260,
          fill: '#082858',
        },
        {
          type: 'Textbox',
          hmId: 'title',
          binding: 'title',
          hmFlowRow: -1,
          text: 'AX 개발자',
          left: 40,
          top: 96,
          width: 450,
          fontSize: 40,
          fill: '#ffffff',
        },
        {
          type: 'Textbox',
          hmId: 'company',
          binding: 'company',
          hmFlowRow: -1,
          text: '동찬리은행',
          left: 40.7,
          top: companyTop,
          width: 69.9,
          fontSize: 21.6,
          fill: '#ffffff',
        },
        {
          type: 'Textbox',
          hmId: 'tags',
          binding: 'tags',
          hmFlowRow: -1,
          text: 'AX 개발자 · 경력 1년 이상 · 서울 본사',
          left: 40,
          top: 180,
          width: 520,
          fontSize: 13,
          fill: '#ffffff',
        },
        {
          type: 'Textbox',
          hmId: 'intro',
          binding: 'intro',
          hmFlowRow: 0,
          text: '회사 소개\n1967년 지역 상호금융에서 출발한 시중은행입니다.',
          left: 40,
          top: 318,
          width: 520,
          fontSize: 14,
          fill: '#24313e',
        },
      ].map((object) => ({ ...object, originX: 'left', originY: 'top', splitByGrapheme: true })),
    }
    const target = new F.StaticCanvas(document.createElement('canvas'), {
      width: doc.width,
      height: doc.height,
    })
    try {
      await target.loadFromJSON({ objects: doc.objects })
      const initial = target.getObjects()
      await layoutCanvaPoster(target, doc)
      const [header, title, company, tags, intro] = initial
      expect(company.width).toBeGreaterThanOrEqual(200)
      for (const node of [title, company, tags]) {
        expect(node.top + node.getScaledHeight() + 24).toBeLessThan(header.getScaledHeight())
        expect(intro.top).toBeGreaterThan(node.top + node.getScaledHeight() + 24)
      }
      const text = [title, company, tags, intro]
      for (let i = 0; i < text.length; i++)
        for (let j = i + 1; j < text.length; j++) {
          const a = text[i].getBoundingRect(),
            b = text[j].getBoundingRect()
          expect(
            a.left + a.width <= b.left ||
              b.left + b.width <= a.left ||
              a.top + a.height <= b.top ||
              b.top + b.height <= a.top,
          ).toBe(true)
        }
      expect(company.fill).toBe('#ffffff')
      expect(intro.fill).toBe('#24313e')
    } finally {
      await target.dispose()
    }
  },
)
