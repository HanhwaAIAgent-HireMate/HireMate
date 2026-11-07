import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { StaticCanvas } from 'fabric'
import { ORSHOT_SOURCE_LAYOUTS } from './orshot-source-layouts'
import type { PosterCanvas } from './poster-canvas'
import { posterBindings } from './poster-canvas'
import type { PosterPosting } from './PostingPoster'
import type { PosterDesign } from './poster-design'
import { conditionRows } from './conditions'
import { POSTER_FONT } from './poster-svg'
import { resolvedStageIcon, STAGE_ICONS } from '@/features/recruit/stage-icons'

type Bounds = { left: number; top: number; width: number; height: number }
type SourceText = Bounds & {
  size: number
  color: string
  weight: string
  serif: boolean
  align?: 'left' | 'center' | 'right'
}
type SourceHeading = SourceText & { label: string }
type SourceShape = Bounds & {
  fill: string
  radius: number
  stroke: string | null
  strokeWidth: number
  dash: boolean
}
export type OrshotSourceLayout = {
  paper: string
  headerHeight: number
  sections: { binding: string; heading: SourceHeading; body: SourceText; shapes: SourceShape[] }[]
  stages: {
    heading: SourceHeading
    cells: { shape: SourceShape; label: SourceText; numbered: boolean }[]
  }
  documents: { heading: SourceHeading; shape: SourceShape; body: SourceText }
}

/** 출처에 실제로 있던 서체·카드·단 구성으로 그리고, 글이 늘어난 높이만 다음 행으로 전달한다. */
export async function layoutOrshotSource(
  target: StaticCanvas,
  doc: PosterCanvas,
  posting: PosterPosting,
  design: PosterDesign | undefined,
) {
  const source = ORSHOT_SOURCE_LAYOUTS[doc.nativeLayout?.sourceTemplate ?? '']
  if (!source) throw new Error('원본 본문 구성을 확인하지 못했어요.')
  const F = await import('fabric')
  const values = posterBindings(posting, design)
  values.conditions = [
    { label: '고용 형태', value: posting.content.employmentType },
    { label: '경력', value: posting.content.career },
    { label: '근무지', value: posting.content.location },
    ...conditionRows(posting.content),
  ]
    .filter((row) => row.value)
    .map((row) => `${row.label}  ${row.value}`)
    .join('\n')
  const recoloring = design?.color && doc.brandColor && design.color !== doc.brandColor
  const color = (fill: string) =>
    recoloring && fill.toLowerCase() === doc.brandColor?.toLowerCase() ? design.color : fill
  const text = (
    value: string,
    style: SourceText,
    top: number,
    binding: string,
    left = style.left,
    width = style.width,
  ) => {
    const node = new F.Textbox(value, {
      left,
      top,
      width,
      fontSize: Math.max(13, style.size),
      fontWeight: style.weight,
      fontFamily: style.serif ? 'serif' : POSTER_FONT,
      textAlign: style.align ?? 'left',
      fill: color(style.color),
      lineHeight: 1.3,
      splitByGrapheme: true,
      originX: 'left',
      originY: 'top',
    })
    node.set('hmId', binding)
    node.set('hmNativeBody', true)
    target.add(node)
    return node
  }
  const shape = (style: SourceShape, top: number, growth: number, binding: string) => {
    const node = new F.Rect({
      left: style.left,
      top,
      width: style.width,
      height: style.height + growth,
      rx: style.radius,
      ry: style.radius,
      fill: color(style.fill),
      stroke: style.stroke ? color(style.stroke) : undefined,
      strokeWidth: style.strokeWidth,
      strokeDashArray: style.dash ? [4, 3] : undefined,
      originX: 'left',
      originY: 'top',
    })
    node.set('hmId', binding)
    node.set('hmNativeBody', true)
    target.add(node)
    return node
  }
  target.set({ backgroundColor: source.paper })
  target
    .getObjects()
    .filter((node) => node.get('hmNativeBody') === true)
    .forEach((node) => target.remove(node))
  const rows: (typeof source.sections)[] = []
  const topOf = (section: (typeof source.sections)[number]) =>
    Math.min(section.heading.top, section.body.top, ...section.shapes.map((s) => s.top))
  const bottomOf = (section: (typeof source.sections)[number]) =>
    Math.max(
      section.heading.top + section.heading.height,
      section.body.top + section.body.height,
      ...section.shapes.map((s) => s.top + s.height),
    )
  for (const section of source.sections) {
    if (!values[section.binding]) continue
    const row = rows.find((r) => Math.abs(topOf(r[0]) - topOf(section)) < 10)
    if (row) row.push(section)
    else rows.push([section])
  }
  rows.sort((a, b) => topOf(a[0]) - topOf(b[0]))
  let cursor = source.headerHeight
  let originalBottom = source.headerHeight
  for (const row of rows) {
    const originalTop = Math.min(...row.map(topOf))
    cursor += Math.max(16, originalTop - originalBottom)
    let actualBottom = cursor
    for (const section of row) {
      const shift = cursor - originalTop
      const content = values[section.binding]
      const label = section.heading.label.replace(/^\d+\s*/, '')
      const body = content.startsWith(label + '\n')
        ? content.slice(content.indexOf('\n') + 1)
        : content
      const edited = doc.nativeLayout?.sections.find((item) => item.binding === section.binding)
      const override = doc.objects.find(
        (item) => item.binding === section.binding && item.hmNativeBody === true,
      )
      const bodyStyle: SourceText = {
        ...section.body,
        ...(override
          ? {
              size: Number(override.fontSize ?? section.body.size),
              color: typeof override.fill === 'string' ? override.fill : section.body.color,
              weight:
                typeof override.fontWeight === 'string' || typeof override.fontWeight === 'number'
                  ? String(override.fontWeight)
                  : section.body.weight,
              serif: override.fontFamily === 'serif',
              align:
                override.textAlign === 'center' || override.textAlign === 'right'
                  ? override.textAlign
                  : 'left',
            }
          : {}),
      }
      const headingStyle: SourceText = {
        ...section.heading,
        ...(edited
          ? {
              size: edited.heading.fontSize,
              color: edited.heading.fill,
              weight: edited.heading.fontWeight,
              serif: edited.heading.fontFamily === 'serif',
            }
          : {}),
      }
      const heading = text(
        section.heading.label,
        headingStyle,
        section.heading.top + shift,
        section.binding,
      )
      // 제목을 키워도 본문과 겹치지 않도록 실제 높이를 보고 같은 영역을 늘린다.
      const headingGrowth = Math.max(0, heading.height - section.heading.height)
      const stacked = section.body.top >= section.heading.top + section.heading.height - 2
      const bodyNode = text(
        body,
        bodyStyle,
        section.body.top + shift + (stacked ? headingGrowth : 0),
        section.binding,
      )
      const growth = Math.max(
        0,
        bodyNode.height + (stacked ? headingGrowth : 0) - section.body.height,
        headingGrowth,
      )
      let firstText = target.getObjects().indexOf(heading)
      for (const decoration of section.shapes) {
        const box = shape(
          decoration,
          decoration.top + shift,
          decoration.top + decoration.height > section.body.top + 1
            ? growth
            : decoration.height > 3 && decoration.top <= section.heading.top
              ? headingGrowth
              : 0,
          section.binding,
        )
        target.moveObjectTo(box, firstText++)
      }
      actualBottom = Math.max(actualBottom, bottomOf(section) + shift + growth)
    }
    cursor = actualBottom
    originalBottom = Math.max(...row.map(bottomOf))
  }
  const process = source.stages
  cursor += Math.max(24, process.heading.top - originalBottom)
  const processHeading = text(process.heading.label, process.heading, cursor, 'stages')
  cursor += Math.max(process.heading.height, processHeading.height) + 18
  const stages = [
    ...posting.stages,
    { name: '최종 합격', type: 'INTERVIEW' as const, icon: 'BADGE_CHECK' as const },
  ]
  const columns = process.cells.length
  for (let offset = 0; offset < stages.length; offset += columns) {
    const labels = stages.slice(offset, offset + columns).map((stage, index) => {
      const final = offset + index === stages.length - 1
      const original = process.cells[final ? columns - 1 : index]
      const position = process.cells[index]
      const cell = { ...original, shape: { ...original.shape, left: position.shape.left } }
      const label = text(
        `${cell.numbered ? `${offset + index + 1} / ` : ''}${stage.name}`,
        cell.label,
        cursor + 27,
        `stage:${stage.name}`,
        cell.shape.left + 10,
        cell.shape.width - 20,
      )
      return { stage, cell, label, final }
    })
    const height = Math.max(
      ...labels.map(({ cell, label }) => Math.max(cell.shape.height, 37 + label.height)),
    )
    for (const { stage, cell, label, final } of labels) {
      const background = shape(
        cell.shape,
        cursor,
        height - cell.shape.height,
        `stage:${stage.name}`,
      )
      target.moveObjectTo(background, target.getObjects().indexOf(label))
      const icon = resolvedStageIcon(
        stage.type ?? 'INTERVIEW',
        final ? 'BADGE_CHECK' : design?.stageIcons?.[stage.name],
        stage.name,
      )
      const Component = STAGE_ICONS.find((item) => item.id === icon)?.component
      if (Component) {
        const loaded = await F.loadSVGFromString(
          renderToStaticMarkup(
            createElement(Component, { size: 16, color: color(cell.label.color) }),
          ),
        )
        const group = F.util.groupSVGElements(
          loaded.objects.filter((node) => node !== null),
          loaded.options,
        )
        group.set({
          left: cell.shape.left + 10,
          top: cursor + 7,
          originX: 'left',
          originY: 'top',
          hmId: `stage:${stage.name}`,
          hmNativeBody: true,
        })
        target.add(group)
      }
    }
    cursor += height + 14
  }
  const documents = source.documents
  cursor += 20
  const docsHeading = text(documents.heading.label, documents.heading, cursor, 'documents')
  cursor += Math.max(documents.heading.height, docsHeading.height) + 16
  const bodyTop = cursor + Math.max(12, documents.body.top - documents.shape.top)
  const docs = posting.documents
    .map(
      (item) =>
        `${item.label} (${item.format === 'TEXT' ? '텍스트' : item.format} · ${item.required ? '필수' : '선택'})`,
    )
    .join('  ·  ')
  const body = text(docs, documents.body, bodyTop, 'documents')
  const bandHeight = Math.max(documents.shape.height, body.height + bodyTop - cursor + 12)
  const band = shape(
    documents.shape,
    cursor,
    documents.shape.height <= 3 ? 0 : bandHeight - documents.shape.height,
    'documents',
  )
  target.moveObjectTo(band, target.getObjects().indexOf(body))
  cursor = Math.max(cursor + bandHeight, body.top + body.height) + 36
  for (const [binding, label] of [
    ['period', '접수 기간'],
    ['notices', '유의사항'],
  ]) {
    if (!values[binding]) continue
    const heading = text(label, documents.heading, cursor, binding)
    const content = text(
      values[binding].replace(new RegExp(`^${label}\\n`), ''),
      documents.body,
      cursor + heading.height + 14,
      binding,
    )
    cursor = content.top + content.height + 32
  }
  if (cursor > 20000) throw new Error('공고가 너무 길어 원본 형식으로 배치하지 못했어요.')
  target.setDimensions({ height: cursor + 20 })
  target.getObjects().forEach((node) => node.setCoords())
}
