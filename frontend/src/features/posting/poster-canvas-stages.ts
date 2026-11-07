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
    variant?: 'CARDS' | 'TIMELINE' | 'STEPS' | 'CHEVRONS' | 'RAIL' | 'BADGES'
    paper?: string
    refined?: boolean
  },
) {
  const F = await import('fabric')
  const items = [
    ...posting.stages,
    { name: '최종 합격', type: 'INTERVIEW' as const, icon: 'BADGE_CHECK' as const },
  ]
  if (style.variant && ['CHEVRONS', 'RAIL', 'BADGES'].includes(style.variant)) {
    const rail = style.variant === 'RAIL'
    const columns = rail ? 1 : Math.min(style.variant === 'BADGES' ? 3 : 4, items.length)
    const gap = 12,
      cellWidth = (width - gap * (columns - 1)) / columns
    let height = 0
    for (let offset = 0; offset < items.length; offset += columns) {
      const cells = items.slice(offset, offset + columns).map((stage, index) => {
        const final = offset + index === items.length - 1
        const fill = final ? style.final : style.card
        const rgb = new F.Color(fill).getSource()
        const ink =
          rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722 < 150 ? '#ffffff' : '#17212b'
        const x = left + index * (cellWidth + gap)
        const label = new F.Textbox(stage.name, {
          left: x + (rail ? 64 : 14),
          top: top + height + (rail ? 20 : 48),
          width: cellWidth - (rail ? 82 : 28),
          fontFamily: POSTER_FONT,
          fontSize: 12,
          fontWeight: '600',
          fill: ink,
          splitByGrapheme: true,
          lineHeight: 1.4,
          originX: 'left',
          originY: 'top',
        })
        label.set('hmId', `stage:${stage.name}`)
        return { stage, final, fill, ink, x, label }
      })
      const rowHeight = Math.max(
        rail ? 64 : 94,
        ...cells.map((cell) => cell.label.height + (rail ? 38 : 62)),
      )
      for (const cell of cells) {
        const shape =
          style.variant === 'CHEVRONS'
            ? new F.Polygon(
                [
                  { x: 0, y: 0 },
                  { x: cellWidth - 12, y: 0 },
                  { x: cellWidth, y: rowHeight / 2 },
                  { x: cellWidth - 12, y: rowHeight },
                  { x: 0, y: rowHeight },
                  { x: 10, y: rowHeight / 2 },
                ],
                {
                  left: cell.x,
                  top: top + height,
                  fill: cell.fill,
                  strokeWidth: 0,
                  originX: 'left',
                  originY: 'top',
                },
              )
            : new F.Rect({
                left: cell.x,
                top: top + height,
                width: cellWidth,
                height: rowHeight,
                fill: cell.fill,
                rx: style.variant === 'BADGES' ? rowHeight / 2 : 0,
                ry: style.variant === 'BADGES' ? rowHeight / 2 : 0,
                strokeWidth: 0,
                originX: 'left',
                originY: 'top',
              })
        shape.set('hmId', `stage:${cell.stage.name}`)
        target.add(shape, cell.label)
        const icon = resolvedStageIcon(
          cell.stage.type ?? 'INTERVIEW',
          cell.final ? 'BADGE_CHECK' : design.stageIcons?.[cell.stage.name],
          cell.stage.name,
        )
        const Component = STAGE_ICONS.find((item) => item.id === icon)?.component
        if (Component) {
          const loaded = await F.loadSVGFromString(
            renderToStaticMarkup(createElement(Component, { color: cell.ink, size: 22 })),
          )
          const group = F.util.groupSVGElements(
            loaded.objects.filter((node) => node !== null),
            loaded.options,
          )
          group.set({
            left: cell.x + (rail ? 20 : 14),
            top: top + height + (rail ? 20 : 14),
            originX: 'left',
            originY: 'top',
          })
          group.set('hmId', `stage:${cell.stage.name}`)
          target.add(group)
        }
      }
      height += rowHeight + gap
    }
    return height
  }
  if (style.refined)
    return drawRefinedStages(target, items, design, left, top, width, {
      ...style,
      variant: style.variant === 'TIMELINE' || style.variant === 'STEPS' ? style.variant : 'CARDS',
    })
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

async function drawRefinedStages(
  target: StaticCanvas,
  items: PosterPosting['stages'],
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
  const paper = style.paper ?? '#ffffff'
  const ink = (color: string) => {
    const [r, g, b] = new F.Color(color)
      .getSource()
      .slice(0, 3)
      .map((value) => {
        const channel = value / 255
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
      })
    return r * 0.2126 + g * 0.7152 + b * 0.0722 < 0.179 ? '#ffffff' : '#17212b'
  }
  const blend = (amount: number) => {
    const brand = new F.Color(style.card).getSource(),
      base = new F.Color(paper).getSource()
    return `rgb(${brand
      .slice(0, 3)
      .map((channel, index) => Math.round(channel * amount + base[index] * (1 - amount)))
      .join(',')})`
  }
  const text = (
    value: string,
    x: number,
    y: number,
    w: number,
    id: string,
    size = 12,
    fill = ink(paper),
    align: 'left' | 'center' = 'left',
  ) => {
    const node = new F.Textbox(value, {
      left: x,
      top: y,
      width: w,
      fontSize: size,
      fontFamily: POSTER_FONT,
      fontWeight: '600',
      fill,
      textAlign: align,
      splitByGrapheme: true,
      lineHeight: 1.45,
      originX: 'left',
      originY: 'top',
    })
    node.set('hmId', id)
    target.add(node)
    return node
  }
  const addIcon = async (
    stage: PosterPosting['stages'][number],
    final: boolean,
    x: number,
    y: number,
    color: string,
    id: string,
  ) => {
    const icon = resolvedStageIcon(
      stage.type ?? 'INTERVIEW',
      final ? 'BADGE_CHECK' : design.stageIcons?.[stage.name],
      stage.name,
    )
    const Component = STAGE_ICONS.find((item) => item.id === icon)?.component
    if (!Component) return
    const loaded = await F.loadSVGFromString(
      renderToStaticMarkup(createElement(Component, { color, size: 22 })),
    )
    const group = F.util.groupSVGElements(
      loaded.objects.filter((node) => node !== null),
      loaded.options,
    )
    group.set({ left: x, top: y, originX: 'left', originY: 'top' })
    group.set('hmId', id)
    target.add(group)
  }
  const line = (coordinates: [number, number, number, number], color = blend(0.25)) =>
    target.add(new F.Line(coordinates, { stroke: color, strokeWidth: 0.8 }))
  const vertical = style.variant === 'STEPS',
    timeline = style.variant === 'TIMELINE'
  const columns = vertical ? 1 : Math.ceil(items.length / Math.ceil(items.length / 5)),
    gap = 14
  const cellWidth = (width - gap * (columns - 1)) / columns
  let height = 0,
    previousCenter: number | undefined
  for (let offset = 0; offset < items.length; offset += columns) {
    const group = items.slice(offset, offset + columns)
    const rowStart = left + (width - (group.length * cellWidth + (group.length - 1) * gap)) / 2
    const cells = group.map((stage, index) => {
      const x = rowStart + index * (cellWidth + gap),
        final = offset + index === items.length - 1
      const id = `stage:${stage.name}`,
        fill = final ? style.card : paper
      const label = text(
        stage.name,
        vertical ? x + 104 : timeline ? x : x + 12,
        top + height + (vertical ? 16 : timeline ? 77 : 49),
        vertical ? width - 116 : timeline ? cellWidth : cellWidth - 24,
        id,
        vertical ? 13 : 12,
        vertical || timeline ? ink(paper) : ink(fill),
        timeline ? 'center' : 'left',
      )
      return { stage, x, final, id, fill, label }
    })
    const rowHeight = Math.max(
      vertical ? 58 : timeline ? 112 : 96,
      ...cells.map((cell) => cell.label.height + (vertical ? 32 : timeline ? 88 : 65)),
    )
    for (const [index, cell] of cells.entries()) {
      const y = top + height,
        number = String(offset + index + 1).padStart(2, '0')
      if (vertical) {
        const center = y + 29
        if (previousCenter !== undefined)
          line([cell.x + 24, previousCenter + 16, cell.x + 24, center - 16])
        const dot = new F.Circle({
          left: cell.x + 8,
          top: y + 13,
          originX: 'left',
          originY: 'top',
          radius: 16,
          fill: cell.final ? style.card : paper,
          stroke: blend(0.5),
          strokeWidth: 1,
        })
        dot.set('hmId', cell.id)
        target.add(dot)
        text(
          number,
          cell.x + 8,
          y + 21,
          32,
          cell.id,
          10,
          cell.final ? ink(style.card) : ink(paper),
          'center',
        )
        await addIcon(cell.stage, cell.final, cell.x + 62, y + 18, ink(paper), cell.id)
        line([cell.x + 60, y + rowHeight - 1, cell.x + width, y + rowHeight - 1])
        previousCenter = center
      } else if (timeline) {
        const center = cell.x + cellWidth / 2
        if (index < cells.length - 1)
          line([center + 22, y + 42, center + cellWidth + gap - 22, y + 42])
        const circleFill = cell.final ? style.card : blend(0.08)
        const dot = new F.Circle({
          left: center - 22,
          top: y + 20,
          originX: 'left',
          originY: 'top',
          radius: 22,
          fill: circleFill,
          strokeWidth: 0,
        })
        dot.set('hmId', cell.id)
        target.add(dot)
        text(number, cell.x, y, cellWidth, cell.id, 10, ink(paper), 'center')
        await addIcon(cell.stage, cell.final, center - 11, y + 31, ink(circleFill), cell.id)
      } else {
        const card = new F.Rect({
          left: cell.x,
          top: y,
          originX: 'left',
          originY: 'top',
          width: cellWidth,
          height: rowHeight,
          fill: cell.fill,
          stroke: blend(0.3),
          strokeWidth: 0.7,
          rx: 5,
          ry: 5,
        })
        card.set('hmId', cell.id)
        target.add(card)
        target.moveObjectTo(card, target.getObjects().indexOf(cell.label))
        text(number, cell.x + 12, y + 13, 32, cell.id, 10, ink(cell.fill))
        await addIcon(
          cell.stage,
          cell.final,
          cell.x + cellWidth - 34,
          y + 12,
          ink(cell.fill),
          cell.id,
        )
        if (index < cells.length - 1)
          text(
            '›',
            cell.x + cellWidth + 3,
            y + rowHeight / 2 - 12,
            8,
            cell.id,
            17,
            ink(paper),
            'center',
          )
      }
    }
    height += rowHeight + (vertical ? 12 : 20)
  }
  return Math.max(0, height - (vertical ? 12 : 20))
}
