import { expect, it } from 'vitest'
import { drawCanvasDocuments } from './poster-canvas-documents'
import { drawCanvasStages } from './poster-canvas-stages'
import { initialPoster } from './poster-design'
import type { PosterPosting } from './PostingPoster'

const documents: PosterPosting['documents'] = [
  {
    type: 'RESUME',
    label: '경력 사항과 담당 업무를 포함한 자유양식 이력서'.repeat(5),
    format: 'PDF',
    required: true,
  },
  { type: 'COVER_LETTER', label: '자기소개서', format: 'PDF', required: true },
  {
    type: 'PORTFOLIO',
    label: '문제 해결 과정과 본인 역할을 기재한 프로젝트 포트폴리오'.repeat(3),
    format: 'PDF',
    required: false,
  },
  { type: 'CERTIFICATE', label: '자격증', format: 'TEXT', required: false },
]

it.each(['TILES', 'LIST', 'COMPACT', 'TICKETS', 'CHECKLIST', 'ROWS'] as const)(
  '%s 서류 디자인은 긴 이름·형식·필수 여부를 겹침 없이 보존한다',
  async (variant) => {
    const F = await import('fabric')
    const target = new F.StaticCanvas(document.createElement('canvas'), {
      width: 600,
      height: 15000,
    })
    try {
      const height = await drawCanvasDocuments(target, documents, 40, 50, 520, {
        variant,
        primary: '#082858',
        ink: '#17212b',
        rule: '#ccd7e5',
        paper: '#faf9f5',
        fontSize: 14,
      })
      const texts = target
        .getObjects()
        .filter((node): node is InstanceType<typeof F.Textbox> => node instanceof F.Textbox)
      const visible = texts.map((node) => node.text).join('\n')
      for (const doc of documents) expect(visible).toContain(doc.label)
      expect(visible).toContain('필수')
      expect(visible).toContain('선택')
      expect(visible).toContain('TEXT')
      for (const node of texts) {
        const box = node.getBoundingRect()
        expect(box.left).toBeGreaterThanOrEqual(40)
        expect(box.left + box.width).toBeLessThanOrEqual(561)
        expect(box.top + box.height).toBeLessThanOrEqual(50 + height)
      }
      for (let i = 0; i < texts.length; i++)
        for (let j = i + 1; j < texts.length; j++) {
          const a = texts[i].getBoundingRect(),
            b = texts[j].getBoundingRect()
          expect(
            a.left + a.width <= b.left ||
              b.left + b.width <= a.left ||
              a.top + a.height <= b.top ||
              b.top + b.height <= a.top,
            `${texts[i].text} / ${texts[j].text}`,
          ).toBe(true)
        }
    } finally {
      await target.dispose()
    }
  },
)

it.each(['CARDS', 'TIMELINE', 'STEPS', 'CHEVRONS', 'RAIL', 'BADGES'] as const)(
  '%s 전형 디자인은 많은 단계와 긴 이름을 자르지 않고 아이콘 수정도 유지한다',
  async (variant) => {
    const F = await import('fabric')
    const stages: PosterPosting['stages'] = [
      { name: '서류 전형', type: 'DOCUMENT' },
      { name: '직무역량 평가 및 과제 제출 안내', type: 'ASSESSMENT' },
      { name: '1차 면접', type: 'INTERVIEW' },
      { name: '2차 면접 및 조직문화 적합성 심층 대화', type: 'INTERVIEW' },
      { name: '추가 면접', type: 'INTERVIEW' },
      { name: '최종면접', type: 'INTERVIEW' },
    ]
    const posting = { stages } as PosterPosting
    const target = new F.StaticCanvas(document.createElement('canvas'), {
      width: 600,
      height: 15000,
    })
    try {
      const height = await drawCanvasStages(
        target,
        posting,
        { ...initialPoster(), stageIcons: { '1차 면접': 'USERS' } },
        40,
        30,
        520,
        {
          variant,
          refined: true,
          card: '#082858',
          final: '#b59a58',
          paper: '#faf9f5',
          fontSize: 14,
        },
      )
      const texts = target
        .getObjects()
        .filter((node): node is InstanceType<typeof F.Textbox> => node instanceof F.Textbox)
      const visible = texts.map((node) => node.text).join('\n')
      for (const stage of stages) expect(visible).toContain(stage.name)
      expect(visible).toContain('최종 합격')
      for (const node of texts) {
        const box = node.getBoundingRect()
        expect(box.left).toBeGreaterThanOrEqual(40)
        expect(box.left + box.width).toBeLessThanOrEqual(561)
        expect(box.top + box.height).toBeLessThanOrEqual(30 + height)
      }
      for (let i = 0; i < texts.length; i++)
        for (let j = i + 1; j < texts.length; j++) {
          const a = texts[i].getBoundingRect(),
            b = texts[j].getBoundingRect()
          expect(
            a.left + a.width <= b.left ||
              b.left + b.width <= a.left ||
              a.top + a.height <= b.top ||
              b.top + b.height <= a.top,
            `${texts[i].text} / ${texts[j].text}`,
          ).toBe(true)
        }
      expect(
        target
          .getObjects()
          .filter((node) => node.type === 'group' && node.get('hmId') === 'stage:1차 면접'),
      ).toHaveLength(1)
      for (const shape of target
        .getObjects()
        .filter((node) => ['rect', 'circle'].includes(node.type))) {
        const bounds = shape.getBoundingRect()
        expect(bounds.left).toBeGreaterThanOrEqual(39)
        expect(bounds.top).toBeGreaterThanOrEqual(29)
        expect(bounds.left + bounds.width).toBeLessThanOrEqual(561)
        const related = target
          .getObjects()
          .filter((node) => node !== shape && node.get('hmId') === shape.get('hmId'))
        if (variant === 'CARDS')
          for (const node of related.filter(
            (node) => node.type === 'group' || (node instanceof F.Textbox && node.text !== '›'),
          )) {
            const child = node.getBoundingRect()
            expect(child.left).toBeGreaterThanOrEqual(bounds.left)
            expect(child.top).toBeGreaterThanOrEqual(bounds.top)
            expect(child.left + child.width).toBeLessThanOrEqual(bounds.left + bounds.width)
            expect(child.top + child.height).toBeLessThanOrEqual(bounds.top + bounds.height)
          }
        else
          for (const node of related.filter(
            (node) => node.type === 'group' && variant === 'TIMELINE',
          )) {
            const child = node.getBoundingRect()
            expect(child.left).toBeGreaterThanOrEqual(bounds.left)
            expect(child.top).toBeGreaterThanOrEqual(bounds.top)
            expect(child.left + child.width).toBeLessThanOrEqual(bounds.left + bounds.width)
            expect(child.top + child.height).toBeLessThanOrEqual(bounds.top + bounds.height)
          }
      }
      expect(stages).toHaveLength(6)
    } finally {
      await target.dispose()
    }
  },
)
