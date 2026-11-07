import type { StaticCanvas } from 'fabric'
import type { PosterPosting } from './PostingPoster'
import { POSTER_FONT } from './poster-svg'

/** 제출 문구와 필수 여부는 원본 그대로 두고, 서류명 길이를 실측해 하단을 조판한다. */
export async function drawCanvasDocuments(
  target: StaticCanvas,
  documents: PosterPosting['documents'],
  left: number,
  top: number,
  width: number,
  style: {
    variant: 'TILES' | 'LIST' | 'COMPACT' | 'TICKETS' | 'CHECKLIST' | 'ROWS'
    primary: string
    ink: string
    rule: string
    paper: string
    fontSize: number
  },
) {
  const F = await import('fabric')
  const size = Math.max(12, Math.min(15, style.fontSize))
  const text = (
    value: string,
    x: number,
    y: number,
    available: number,
    fontSize = size,
    weight = '400',
    fill = style.ink,
  ) => {
    const node = new F.Textbox(value, {
      left: x,
      top: y,
      width: available,
      fontSize,
      fontFamily: POSTER_FONT,
      fontWeight: weight,
      fill,
      lineHeight: 1.5,
      splitByGrapheme: true,
      originX: 'left',
      originY: 'top',
    })
    node.set('hmId', 'documents')
    target.add(node)
    return node
  }
  const box = (x: number, y: number, w: number, h: number, fill: string, stroke?: string) => {
    const node = new F.Rect({
      left: x,
      top: y,
      width: w,
      height: h,
      fill,
      stroke,
      strokeWidth: stroke ? 0.7 : 0,
      originX: 'left',
      originY: 'top',
      rx: style.variant === 'TILES' ? 5 : 0,
      ry: style.variant === 'TILES' ? 5 : 0,
    })
    node.set('hmId', 'documents')
    target.add(node)
    return node
  }
  let height = 0
  if (['TICKETS', 'CHECKLIST', 'ROWS'].includes(style.variant)) {
    const columns = style.variant === 'ROWS' && width >= 400 ? 3 : 1
    const gap = 12,
      cellWidth = (width - gap * (columns - 1)) / columns
    for (let offset = 0; offset < documents.length; offset += columns) {
      const cells = documents.slice(offset, offset + columns).map((document, index) => {
        const x = left + index * (cellWidth + gap)
        const label = text(document.label, x + 38, top + height + 12, cellWidth - 52, size, '600')
        return { document, x, label }
      })
      const rowHeight = Math.max(74, ...cells.map((cell) => cell.label.height + 42))
      for (const cell of cells) {
        const card = box(cell.x, top + height, cellWidth, rowHeight, style.paper, style.rule)
        target.moveObjectTo(card, target.getObjects().indexOf(cell.label))
        text(
          style.variant === 'CHECKLIST'
            ? '✓'
            : String(offset + cells.indexOf(cell) + 1).padStart(2, '0'),
          cell.x + 12,
          top + height + 15,
          22,
          13,
          '600',
          style.primary,
        )
        text(
          `${cell.document.format} · ${cell.document.required ? '필수' : '선택'}`,
          cell.x + 38,
          top + height + rowHeight - 25,
          cellWidth - 52,
          10,
        )
        if (style.variant === 'TICKETS') {
          for (const x of [cell.x - 4, cell.x + cellWidth - 4]) {
            const hole = new F.Circle({
              left: x,
              top: top + height + rowHeight / 2 - 4,
              radius: 4,
              fill: style.paper,
              stroke: style.rule,
              strokeWidth: 0.7,
            })
            hole.set('hmId', 'documents')
            target.add(hole)
          }
          box(cell.x + cellWidth - 18, top + height + 10, 2, rowHeight - 20, style.rule)
        } else if (style.variant === 'ROWS') box(cell.x, top + height, cellWidth, 4, style.primary)
      }
      height += rowHeight + gap
    }
    return height
  }
  if (style.variant === 'TILES') {
    const columns = width >= 400 ? 2 : 1,
      gap = 14
    const cellWidth = (width - gap * (columns - 1)) / columns
    for (let offset = 0; offset < documents.length; offset += columns) {
      const cells = documents.slice(offset, offset + columns).map((document, index) => {
        const x = left + index * (cellWidth + gap),
          y = top + height
        const name = text(document.label, x + 16, y + 39, cellWidth - 32, size, '600')
        return { document, x, y, name, number: offset + index + 1 }
      })
      const rowHeight = Math.max(112, ...cells.map((cell) => cell.name.height + 82))
      for (const cell of cells) {
        const card = box(cell.x, cell.y, cellWidth, rowHeight, style.paper, style.rule)
        target.moveObjectTo(card, target.getObjects().indexOf(cell.name))
        box(cell.x + 16, cell.y + 17, 18, 2, style.primary)
        text(
          String(cell.number).padStart(2, '0'),
          cell.x + cellWidth - 40,
          cell.y + 14,
          24,
          10,
          '600',
        )
        text(cell.document.format, cell.x + 16, cell.y + rowHeight - 28, cellWidth - 90, 10)
        text(
          cell.document.required ? '필수' : '선택',
          cell.x + cellWidth - 52,
          cell.y + rowHeight - 29,
          36,
          11,
          '600',
        )
      }
      height += rowHeight + 14
    }
    return Math.max(0, height - 14)
  }
  if (style.variant === 'COMPACT') {
    box(left, top, width, 2, style.primary)
    text('서류명', left + 28, top + 13, width * 0.55, 10, '600')
    text('파일 형식', left + width * 0.66, top + 13, width * 0.14, 10, '600')
    text('구분', left + width * 0.85, top + 13, width * 0.13, 10, '600')
    height = 43
  }
  for (const [index, document] of documents.entries()) {
    const y = top + height
    const nameWidth = style.variant === 'COMPACT' ? width * 0.58 - 30 : width - 140
    const name = text(document.label, left + 28, y + 12, nameWidth, size, '600')
    const meta =
      style.variant === 'COMPACT'
        ? text(document.format, left + width * 0.66, y + 12, width * 0.14, 11)
        : text(
            `${document.format} · ${document.required ? '필수' : '선택'}`,
            left + width - 96,
            y + 12,
            92,
            11,
          )
    const rowHeight = Math.max(46, name.height + 24, meta.height + 24)
    text(String(index + 1).padStart(2, '0'), left, y + 14, 20, 10, '600')
    if (style.variant === 'COMPACT')
      text(
        document.required ? '필수' : '선택',
        left + width * 0.85,
        y + 12,
        width * 0.13,
        11,
        document.required ? '600' : '400',
      )
    box(left, y + rowHeight, width, 0.6, style.rule)
    height += rowHeight
  }
  return height + 1
}
