import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { StaticCanvas } from 'fabric'
import { CanvasPoster } from '@/features/posting/CanvasPoster'
import { initialPoster } from '@/features/posting/poster-design'
import {
  importCanvaPoster,
  importPosterTemplate,
  readPosterCanvas,
} from '@/features/posting/poster-canvas'
import type { PosterPosting } from '@/features/posting/PostingPoster'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it.each(['canva', 'templated'])(
  '%s의 긴 한글 본문을 같은 테마로 이어 그리고 모든 글자를 캔버스 안에 둔다',
  async (provider) => {
    const F = await import('fabric')
    const bitmap = document.createElement('canvas')
    bitmap.width = 600
    bitmap.height = 850
    const pixels = bitmap.getContext('2d')!
    pixels.fillStyle = '#eee8da'
    pixels.fillRect(0, 0, 600, 850)
    const fonts = document.fonts
    Object.defineProperty(document, 'fonts', {
      configurable: true,
      value: { ready: Promise.resolve() },
    })
    vi.spyOn(F.FabricImage, 'fromURL').mockResolvedValue(new F.FabricImage(bitmap))
    vi.spyOn(F.FabricImage, 'fromObject').mockImplementation((options) =>
      Promise.resolve(
        new F.FabricImage(bitmap, {
          left: options.left,
          top: options.top,
          width: options.width,
          height: options.height,
          scaleX: options.scaleX,
          scaleY: options.scaleY,
          originX: 'left',
          originY: 'top',
        }),
      ),
    )
    const content = '복잡한업무도생략없이안전하게수행하고운영하는역량'.repeat(15)
    const posting: PosterPosting = {
      companyName: '우리 은행',
      openAt: null,
      closeAt: null,
      content: {
        title: '마케팅 신입 채용',
        jobCategory: '마케팅',
        career: '신입',
        employmentType: '정규직',
        location: '서울',
        intro: content,
        duties: [content, content],
        qualifications: [content, content],
        preferred: [content],
        benefits: [content],
        roles: [],
        headcount: null,
        position: '',
        education: '',
        workHours: '',
        salary: '',
        blind: false,
      },
      stages: [{ name: '서류' }, { name: '면접' }],
      documents: [{ type: 'RESUME', label: '이력서', format: 'PDF', required: true }],
      notices: [],
    }
    try {
      let canvasJson = await importCanvaPoster(
        {
          template: {
            id: 'DATHEME1',
            name: '원본',
            editUrl: '',
            background: bitmap.toDataURL('image/jpeg'),
            width: 600,
            height: 850,
            regions: [
              { id: 'header', text: '채용', left: 40, top: 60, width: 460, height: 60 },
              { id: 'left', text: '주요 업무 입력', left: 40, top: 260, width: 190, height: 22 },
              { id: 'right', text: '필수 요건 입력', left: 320, top: 264, width: 190, height: 22 },
              { id: 'last', text: '우대 사항', left: 40, top: 520, width: 190, height: 22 },
            ],
          },
          mapping: {
            bindings: [
              { elementId: 'header', binding: 'title' },
              { elementId: 'left', binding: 'duties' },
              { elementId: 'right', binding: 'qualifications' },
              { elementId: 'last', binding: 'preferred' },
            ],
          },
        },
        posting,
        '#123456',
      )
      if (provider === 'templated') {
        canvasJson = await importPosterTemplate(
          {
            id: 'templated:00000000-0000-0000-0000-000000000001',
            name: '외부 테마',
            sourceUrl: 'https://templated.io/templates/',
            license: 'Templated 테마',
            thumbnailUrl: null,
            svg: '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="1200" data-body-top="320"><rect width="600" height="1200" fill="#eee8da"/><rect width="600" height="320" fill="#082858"/><text x="40" y="50">원본 예시 회사 문구</text></svg>',
          },
          posting,
          '#123456',
        )
        expect(canvasJson).not.toContain('원본 예시 회사 문구')
        expect(readPosterCanvas(canvasJson).source.url).toBe('https://templated.io/templates/')
      }
      const imported = readPosterCanvas(canvasJson)
      expect(imported.canvaLayout?.paper).toBe('#eee8da')
      expect(imported.canvaLayout?.headerHeight).toBeLessThan(400)
      expect(imported.objects.find((node) => node.binding === 'duties')?.top).toBe(
        imported.objects.find((node) => node.binding === 'qualifications')?.top,
      )
      let checked = false
      let validationError: unknown
      vi.spyOn(F.StaticCanvas.prototype, 'toSVG').mockImplementation(function (this: StaticCanvas) {
        try {
          const text = this.getObjects().filter((node) => node.type === 'textbox')
          const stages = text.find(
            (node) => node instanceof F.Textbox && node.text.startsWith('전형 절차'),
          )
          const documents = text.find(
            (node) => node instanceof F.Textbox && node.text.startsWith('제출 서류'),
          )
          expect(stages?.left).toBe(74)
          expect(stages?.width).toBe(482)
          expect(documents?.left).toBe(74)
          expect(documents?.width).toBe(482)
          const process = this.getObjects().filter((node) =>
            String(node.get('hmId')).startsWith('stage:'),
          )
          expect(Math.min(...process.map((node) => node.getBoundingRect().left))).toBe(44)
          expect(
            Math.max(
              ...process.map((node) => node.getBoundingRect().left + node.getBoundingRect().width),
            ),
          ).toBeCloseTo(556, 0)
          expect(documents!.top).toBeGreaterThan(stages!.top + stages!.getScaledHeight())
          for (const node of text) {
            const bounds = node.getBoundingRect()
            expect(bounds.left).toBeGreaterThanOrEqual(24)
            expect(bounds.top).toBeGreaterThanOrEqual(24)
            expect(bounds.left + bounds.width).toBeLessThanOrEqual(this.width - 23)
            expect(bounds.top + bounds.height).toBeLessThanOrEqual(this.height - 23)
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
                JSON.stringify({ i, j, a, b }),
              ).toBe(true)
            }
          expect(this.backgroundColor).toBe('#eee8da')
          expect(this.height).toBeGreaterThan(850)
        } catch (error) {
          validationError = error
        }
        checked = true
        return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${this.width}" height="${this.height}">${this.getObjects()
          .map((node) => node.toSVG())
          .join('')}</svg>`
      })
      const view = render(
        <CanvasPoster
          posting={posting}
          design={{ ...initialPoster(), canvasJson, showLogo: false }}
        />,
      )
      await waitFor(() => expect(checked).toBe(true), { timeout: 10000 })
      if (validationError instanceof Error) throw validationError
      if (validationError) throw new Error('포스터 영역 검사 실패')
      expect(view.getByRole('img').querySelector('svg')).toHaveAttribute('width', '100%')
    } finally {
      Object.defineProperty(document, 'fonts', { configurable: true, value: fonts })
    }
  },
)
