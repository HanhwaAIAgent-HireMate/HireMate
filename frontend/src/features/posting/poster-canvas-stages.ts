import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { StaticCanvas } from 'fabric'
import { STAGE_ICONS, resolvedStageIcon } from '@/features/recruit/stage-icons'
import type { PosterPosting } from './PostingPoster'
import type { PosterDesign } from './poster-design'
import { POSTER_FONT } from './poster-svg'

/** 정적 SVG 아이콘을 같은 캔버스에 그려 미리보기·저장·PDF가 같은 전형 그림을 사용한다. */
export async function drawCanvasStages(
  target: StaticCanvas,
  posting: PosterPosting,
  design: PosterDesign,
  left: number,
  top: number,
  width: number,
  style: {
    card: string
    final: string
    fontSize: number
    variant?: 'CARDS' | 'TIMELINE' | 'STEPS'
    paper?: string
  },
) {
  const F = await import('fabric')
  const items = [
    ...posting.stages,
    { name: '최종 합격', type: 'INTERVIEW' as const, icon: 'BADGE_CHECK' as const },
  ]
  const timeline = style.variant === 'TIMELINE',
    vertical = style.variant === 'STEPS'
  const columns = vertical ? 1 : Math.min(items.length, 5),
    gap = 14,
    cellWidth = (width - gap * (columns - 1)) / columns
  let height = 0
  for (let offset = 0; offset < items.length; offset += columns) {
    const cells = items.slice(offset, offset + columns).map((stage, index) => {
      const final = offset + index === items.length - 1
      const fill = final ? style.final : style.card
      const rgb = [1, 3, 5].map((at) => Number.parseInt(fill.slice(at, at + 2), 16) / 255)
      const ink = rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722 < 0.55 ? '#ffffff' : '#101820'
      const x = left + index * (cellWidth + gap)
      const label = new F.Textbox(stage.name, {
        left: vertical ? x + 60 : x + 8,
        top: top + height + (vertical ? 18 : 46),
        width: cellWidth - (vertical ? 76 : 16),
        fontSize: Math.min(14, style.fontSize),
        fontFamily: POSTER_FONT,
        fill: timeline ? '#101820' : ink,
        splitByGrapheme: true,
        lineHeight: 1.4,
        originX: 'left',
        originY: 'top',
      })
      label.set('hmId', `stage:${stage.name}`)
      return { stage, x, label, fill, ink, final }
    })
    const rowHeight = Math.max(
      vertical ? 54 : 84,
      ...cells.map((cell) => cell.label.height + (vertical ? 32 : 56)),
    )
    if (timeline && cells.length > 1)
      target.add(
        new F.Line(
          [
            left + cellWidth / 2,
            top + height + 23,
            left + width - cellWidth / 2,
            top + height + 23,
          ],
          { stroke: style.card, strokeWidth: 2 },
        ),
      )
    for (const cell of cells) {
      const box = timeline
        ? new F.Circle({
            left: cell.x + cellWidth / 2 - 18,
            top: top + height + 5,
            radius: 18,
            fill: cell.fill,
            strokeWidth: 0,
            originX: 'left',
            originY: 'top',
          })
        : new F.Rect({
            left: cell.x,
            top: top + height,
            width: cellWidth,
            height: rowHeight,
            fill: cell.fill,
            rx: vertical ? 0 : 5,
            ry: vertical ? 0 : 5,
            strokeWidth: 0,
            originX: 'left',
            originY: 'top',
          })
      box.set('hmId', `stage:${cell.stage.name}`)
      target.add(box, cell.label)
      const icon = resolvedStageIcon(
        cell.stage.type ?? 'INTERVIEW',
        cell.final ? 'BADGE_CHECK' : design.stageIcons?.[cell.stage.name],
        cell.stage.name,
      )
      const Component = STAGE_ICONS.find((item) => item.id === icon)?.component
      if (Component) {
        const svg = renderToStaticMarkup(createElement(Component, { color: cell.ink, size: 24 }))
        const loaded = await F.loadSVGFromString(svg)
        const group = F.util.groupSVGElements(
          loaded.objects.filter((node) => node !== null),
          loaded.options,
        )
        group.set({
          left: timeline ? cell.x + cellWidth / 2 - 12 : cell.x + 14,
          top: top + height + (vertical ? 14 : 11),
          originX: 'left',
          originY: 'top',
        })
        group.set('hmId', `stage:${cell.stage.name}`)
        target.add(group)
      }
    }
    height += rowHeight + 12
  }
  return height
}
