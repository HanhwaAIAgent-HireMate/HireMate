import type { StaticCanvas } from 'fabric'
import type { PosterCanvas, FreeTemplate } from './poster-canvas'
import { posterBindings, usesPhotoCaption } from './poster-canvas'
import type { PosterPosting } from './PostingPoster'
import type { Schemas } from '@/lib/api/client'
import type { PosterDesign } from './poster-design'
import { drawCanvasStages } from './poster-canvas-stages'
import { drawCanvasDocuments } from './poster-canvas-documents'
import { POSTER_FONT } from './poster-svg'
import { conditionRows } from './conditions'
import { layoutOrshotSource } from './poster-source-layout'

const labels: Record<string, string> = {
  intro: '회사 소개',
  conditions: '모집 조건',
  duties: '주요 업무',
  qualifications: '자격 요건',
  preferred: '우대 사항',
  benefits: '복지 및 혜택',
  stages: '전형 절차',
  documents: '제출 서류',
  notices: '유의사항',
  period: '접수 기간',
}
type TextStyle = {
  fontSize: number
  fill: string
  fontWeight: string
  fontFamily?: string
  textAlign?: 'left' | 'center' | 'right'
}
export type NativeSection = {
  variant?: 'RULE' | 'NUMBER' | 'RIBBON' | 'TILE' | 'QUOTE' | 'CHECKLIST'
  binding: string
  left: number
  top: number
  width: number
  height: number
  heading: TextStyle
  body: TextStyle
  accent: string
  rule: string
  card: string
  lastCard: string
  cardInk: string
}
export type NativeLayout = {
  version: 1
  sourceTemplate?: string
  paper: string
  headerBottom: number
  sections: NativeSection[]
  appearance?: {
    body: 'EDITORIAL' | 'PANELS' | 'SIDEBAR' | 'STRIPES'
    process: 'CARDS' | 'TIMELINE' | 'STEPS' | 'CHEVRONS' | 'RAIL' | 'BADGES'
    documents: 'TILES' | 'LIST' | 'COMPACT' | 'TICKETS' | 'CHECKLIST' | 'ROWS'
    edition?: number
    direction?: string
    expression?: 'CALM' | 'GRAPHIC' | 'TYPE'
  }
}

/** 선택한 원본의 영역만 전달한다. 현재 기업의 사실이나 공고 문구는 코드가 채운다. */
export function nativeRegions(svg: string) {
  const root = parse(svg)
  return [...root.querySelectorAll('[data-layer]')].map((node, index) => ({
    id: `source-${index}`,
    text: node.getAttribute('data-kind') === 'TEXT' ? (node.textContent ?? '') : '',
    kind: node.getAttribute('data-kind') as 'TEXT' | 'SHAPE',
    left: Number(node.getAttribute('data-x')),
    top: Number(node.getAttribute('data-y')),
    width: Number(node.getAttribute('data-width')),
    height: Number(node.getAttribute('data-height')),
  }))
}

function parse(svg: string) {
  const root = new DOMParser().parseFromString(svg, 'image/svg+xml')
  if (
    root.querySelector('parsererror, script, style, image, foreignObject, use') ||
    [...root.querySelectorAll('*')].some((node) =>
      [...node.attributes].some((attr) => /^on|href|src/i.test(attr.name)),
    )
  )
    throw new Error('원본에 지원하지 않는 실행 요소가 있어요.')
  return root
}

export async function importNativePoster(
  template: FreeTemplate,
  plan: Schemas['TemplateLayout'],
  color: string,
) {
  const F = await import('fabric')
  const root = parse(template.svg)
  const source = nativeRegions(template.svg)
  const elements = [...root.querySelectorAll('[data-layer]')]
  const scale = 600 / Number(root.documentElement.getAttribute('width'))
  if (!Number.isFinite(scale) || scale < 0.12 || scale > 2 || elements.length > 150)
    throw new Error('원본 크기를 확인하지 못했어요.')
  const used = new Set<number>()
  const bindings = new Set<string>()
  for (const section of plan.sections) {
    if (bindings.has(section.binding) || !section.elements.includes(section.body))
      throw new Error('모델의 원본 구역 해석을 확인하지 못했어요. 다시 가져와 주세요.')
    bindings.add(section.binding)
    for (const number of section.elements) {
      if (!source[number - 1] || used.has(number)) throw new Error('원본 구역이 중복되어 있어요.')
      used.add(number)
    }
  }
  if (!bindings.has('company') || !bindings.has('title'))
    throw new Error('원본 제목 영역을 찾지 못했어요.')
  const hex = (value: string | null, fallback: string) =>
    value ? `#${new F.Color(value).toHex()}` : fallback
  const style = (number: number | null): TextStyle => {
    const text = number ? elements[number - 1]?.querySelector('text') : null
    return {
      fontSize: Math.max(11, Math.min(80, Number(text?.getAttribute('font-size') ?? 24) * scale)),
      fill: hex(text?.getAttribute('fill') ?? null, '#24313e'),
      fontWeight: text?.getAttribute('font-weight') ?? '400',
    }
  }
  const objects: PosterCanvas['objects'] = []
  const sections: NativeSection[] = []
  const header = plan.sections.filter((s) => ['company', 'title', 'tags'].includes(s.binding))
  const body = plan.sections.filter((s) => !['company', 'title', 'tags'].includes(s.binding))
  const firstBody = Math.min(...body.map((s) => source[(s.heading ?? s.body) - 1].top * scale))
  if (!Number.isFinite(firstBody)) throw new Error('원본 본문 영역을 찾지 못했어요.')
  const headerBottom = Number(root.documentElement.getAttribute('data-body-top')) * scale
  // 제공처의 도형 SVG는 100%를 레이어 크기로 해석한다. Fabric은 기본 100px로 읽으므로 먼저 실수치로 바꾼다.
  for (const node of elements) {
    for (const shape of node.querySelectorAll('[width], [height]')) {
      for (const dimension of ['width', 'height']) {
        const value = shape.getAttribute(dimension)
        if (value?.endsWith('%'))
          shape.setAttribute(
            dimension,
            String(
              (Number.parseFloat(value) / 100) * Number(node.getAttribute(`data-${dimension}`)),
            ),
          )
      }
    }
  }
  elements.forEach((node, index) => node.setAttribute('data-native-index', String(index)))
  const headerNumbers = new Set(
    header.filter((s) => s.binding !== 'tags').flatMap((s) => s.elements),
  )
  // 제목/회사명 옆 장식은 같은 원본 좌표계로 보존한다. 본문 장식과 예시 글자는 별도로 재구성한다.
  const loaded = await F.loadSVGFromString(
    new XMLSerializer().serializeToString(root),
    (element, node) => {
      const owner = element.closest('[data-native-index]')
      if (owner) node.set('id', Number(owner.getAttribute('data-native-index')) + 1)
    },
  )
  for (const node of loaded.objects) {
    if (!node || ['text', 'i-text', 'textbox'].includes(node.type.toLowerCase())) continue
    const index = Number(node.get('id'))
    const region = source[index - 1]
    if (
      !region ||
      (!headerNumbers.has(index) && (region.top + region.height) * scale > headerBottom)
    )
      continue
    node.set({
      left: node.left * scale,
      top: node.top * scale,
      scaleX: node.scaleX * scale,
      scaleY: node.scaleY * scale,
    })
    objects.push({ ...(node.toObject() as Record<string, unknown>), hmId: `native-${index}` })
  }
  for (const section of header) {
    const region = source[section.body - 1]
    const text = new F.Textbox('', {
      left: region.left * scale,
      top: region.top * scale,
      width:
        section.binding === 'tags'
          ? 600 - region.left * scale - 44
          : Math.min(region.width * scale, 600 - region.left * scale - 24),
      ...style(
        section.binding === 'tags' ? header.find((s) => s.binding === 'title')!.body : section.body,
      ),
      ...(section.binding === 'tags' ? { fontSize: 13 } : {}),
      fontFamily: POSTER_FONT,
      originX: 'left',
      originY: 'top',
      splitByGrapheme: true,
      lineHeight: 1.4,
    })
    objects.push({ ...text.toObject(), hmId: section.binding, binding: section.binding })
  }
  for (const section of body) {
    const nodes = section.elements.map((number) => source[number - 1])
    const left = Math.min(...nodes.map((n) => n.left)) * scale
    const top = Math.min(...nodes.map((n) => n.top)) * scale
    const width = Math.min(
      600 - left - 24,
      Math.max(...nodes.map((n) => n.left + n.width)) * scale - left,
    )
    const height = Math.max(...nodes.map((n) => n.top + n.height)) * scale - top
    const shapes = section.elements
      .map((number) => elements[number - 1].querySelector('rect, path, line, polygon'))
      .filter((node) => node !== null)
    const cards = shapes.filter((node) => Number(node.getAttribute('height')) * scale > 25)
    const rule = shapes.find((node) => Number(node.getAttribute('height')) * scale <= 3)
    const number = section.elements.find((number) => /^\d{2}$/.test(source[number - 1].text.trim()))
    sections.push({
      binding: section.binding,
      left,
      top,
      width: Math.max(100, width),
      height,
      heading: style(section.heading),
      body: style(section.body),
      accent: number ? style(number).fill : '#b59a58',
      rule: hex(rule?.getAttribute('fill') ?? rule?.getAttribute('stroke') ?? null, '#8b98a6'),
      card: hex(cards[0]?.getAttribute('fill') ?? null, '#082858'),
      lastCard: hex(cards.at(-1)?.getAttribute('fill') ?? null, '#b59a58'),
      cardInk: style(section.body).fill,
    })
  }
  const paper = hex(root.querySelector('svg > rect')?.getAttribute('fill') ?? null, '#f7f5ef')
  return JSON.stringify({
    width: 600,
    height: Number(root.documentElement.getAttribute('height')) * scale,
    brandColor: color,
    source: {
      id: template.id,
      name: template.name,
      url: template.sourceUrl,
      license: template.license,
    },
    nativeLayout: { version: 1, paper, headerBottom, sections },
    objects,
  } satisfies PosterCanvas)
}

/** 원본 단 구성·번호·구분선·카드를 사용하고 실측한 높이만큼 후속 행을 내린다. */
export async function layoutNativePoster(
  target: StaticCanvas,
  doc: PosterCanvas,
  posting: PosterPosting,
  design?: PosterDesign,
) {
  const F = await import('fabric')
  const layout = doc.nativeLayout
  if (!layout) return
  if (layout.sourceTemplate) {
    await layoutOrshotSource(target, doc, posting, design)
    return
  }
  const designed = (layout.appearance?.edition ?? 0) >= 2
  const modern = (layout.appearance?.edition ?? 0) >= 3
  const planned = (layout.appearance?.edition ?? 0) >= 4
  const orshotPhoto = usesPhotoCaption(doc)
  const values = posterBindings(posting, design)
  const { location, employmentType, career } = posting.content
  const conditions = [
    ...(orshotPhoto || doc.originalRender
      ? [
          { label: '근무지', value: location },
          { label: '고용 형태', value: employmentType },
        ].filter((item) => item.value)
      : []),
    ...conditionRows(posting.content),
  ]
  if (orshotPhoto || doc.originalRender)
    values.conditions = conditions.map(({ label, value }) => `${label}  ${value}`).join('\n')
  const all = [
    'intro',
    'duties',
    'qualifications',
    'preferred',
    'benefits',
    'conditions',
    'period',
    'notices',
    'stages',
    'documents',
  ]
  const sections = layout.sections
    .filter((s) => values[s.binding])
    .map((section): NativeSection => {
      const override = doc.objects.find(
        (object) => object.binding === section.binding && object.hmNativeBody === true,
      )
      if (!override && !modern) return { ...section }
      if (!override)
        return {
          ...section,
          heading: { ...section.heading, fontSize: Math.max(16, section.heading.fontSize) },
          body: { ...section.body, fontSize: Math.max(13, section.body.fontSize) },
        }
      return {
        ...section,
        left: Number(override.left),
        width: Number(override.width),
        top: Number(override.top),
        body: {
          ...section.body,
          fontSize: Number(override.fontSize),
          fill: String(override.fill),
          fontWeight: override.fontWeight === 'bold' ? 'bold' : 'normal',
          fontFamily: override.fontFamily === 'serif' ? 'serif' : POSTER_FONT,
          textAlign:
            override.textAlign === 'center' || override.textAlign === 'right'
              ? override.textAlign
              : 'left',
        },
      }
    })
  target
    .getObjects()
    .filter((_, index) => doc.objects[index]?.hmNativeBody === true)
    .forEach((object) => target.remove(object))
  const exemplar = sections.find((s) => !['stages', 'documents'].includes(s.binding))
  if (!exemplar) throw new Error('원본 본문 스타일을 확인하지 못했어요.')
  let end = Math.max(
    layout.headerBottom + 24,
    ...sections
      .filter((s) => !['stages', 'documents'].includes(s.binding))
      .map((s) => s.top + s.height),
  )
  const sourceStart = Math.min(...sections.map((section) => section.top))
  const sourceIntro = sections.find((section) => section.binding === 'intro')
  for (const binding of all) {
    if (!values[binding] || sections.some((s) => s.binding === binding)) continue
    const position =
      binding === 'intro'
        ? sourceStart - 320
        : binding === 'conditions'
          ? sourceIntro
            ? sourceIntro.top + 11
            : sourceStart - 160
          : end + 32
    sections.push({ ...exemplar, binding, left: 44, top: position, width: 512, height: 120 })
    end += 152
  }
  const regular = sections.filter((s) => !['stages', 'documents'].includes(s.binding))
  const tail = ['stages', 'documents'].flatMap((binding) =>
    sections.filter((s) => s.binding === binding),
  )
  const rows: NativeSection[][] = []
  const margin = modern
    ? Math.max(32, Math.min(48, ...sections.map((section) => section.left)))
    : 40
  const fullWidth = doc.width - margin * 2
  // 목록 전체 길이로 두 단 구성을 풀지 않고, 긴 문장 하나가 있을 때만 폭을 늘린다.
  const longSection = (section: NativeSection) =>
    modern
      ? (values[section.binding] ?? '').split('\n').some((line) => line.length > 150)
      : (values[section.binding]?.length ?? 0) > 240
  const priority = (binding: string) =>
    binding === 'intro'
      ? 0
      : binding === 'conditions'
        ? 1
        : binding === 'period'
          ? 3
          : binding === 'notices'
            ? 4
            : 2
  for (const section of regular.sort(
    (a, b) =>
      (modern && !planned ? priority(a.binding) - priority(b.binding) : 0) ||
      a.top - b.top ||
      a.left - b.left,
  )) {
    if (
      (modern &&
        !planned &&
        ['intro', 'conditions', 'period', 'notices'].includes(section.binding)) ||
      (designed && longSection(section))
    ) {
      rows.push([{ ...section, left: margin, width: fullWidth }])
      continue
    }
    const row = rows.find((row) => Math.abs(row[0].top - section.top) < 10)
    if (
      row &&
      row.every(
        (item) =>
          section.left >= item.left + item.width || item.left >= section.left + section.width,
      )
    )
      row.push(section)
    else rows.push([section])
  }
  if (designed && !modern)
    rows.forEach((row) => {
      if (row.length === 1 && row[0].width < 450)
        row[0] = { ...row[0], left: margin, width: fullWidth }
    })
  if (modern && !planned) {
    const balanced: NativeSection[][] = []
    let columns: NativeSection[] = []
    const flushColumns = () => {
      if (columns.length)
        balanced.push(
          columns.length === 1 ? [{ ...columns[0], left: margin, width: fullWidth }] : columns,
        )
      columns = []
    }
    for (const row of rows) {
      if (row.every((section) => section.width < 450)) columns.push(...row)
      else {
        flushColumns()
        balanced.push(row)
      }
    }
    flushColumns()
    rows.splice(0, rows.length, ...balanced)
  }
  if (planned) {
    for (const row of rows) {
      if (row.length === 1 && row[0].width < fullWidth)
        row[0] = { ...row[0], left: margin, width: fullWidth }
    }
  }
  tail.forEach((s) =>
    rows.push([{ ...s, left: modern ? margin : 44, width: modern ? fullWidth : 512 }]),
  )
  const text = (value: string, left: number, top: number, width: number, style: TextStyle) => {
    const node = new F.Textbox(value, {
      left,
      top,
      width,
      fontFamily: POSTER_FONT,
      ...style,
      ...(style.fontFamily === 'serif' ? {} : { fontFamily: POSTER_FONT }),
      originX: 'left',
      originY: 'top',
      splitByGrapheme: true,
      lineHeight: modern ? 1.55 : designed ? 1.65 : 1.5,
    })
    target.add(node)
    return node
  }
  const rect = (left: number, top: number, width: number, height: number, fill: string) => {
    const node = new F.Rect({
      left,
      top,
      width,
      height,
      fill,
      strokeWidth: 0,
      originX: 'left',
      originY: 'top',
    })
    target.add(node)
    return node
  }
  const ink = (fill: string) => {
    const channels = [1, 3, 5]
      .map((at) => Number.parseInt(fill.slice(at, at + 2), 16) / 255)
      .map((value) => (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4))
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722 < 0.179
      ? '#ffffff'
      : '#101820'
  }
  const readable = (fill: string, paper: string) => {
    const luminance = (color: string) => {
      const [r, g, b] = new F.Color(color).getSource().map((value, index) => {
        if (index === 3) return value
        const channel = value / 255
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
      })
      return r * 0.2126 + g * 0.7152 + b * 0.0722
    }
    const first = luminance(fill),
      second = luminance(paper)
    return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05) >= 4.5
      ? fill
      : ink(paper)
  }
  // 네모/회사명 위치를 바꾸지 않고 제목이 길 때만 뒤의 헤더 정보를 아래로 이동한다.
  const headerObjects = target.getObjects()
  const title =
    headerObjects.find((object) => object.get('hmId') === 'title') ??
    headerObjects.find((_, i) => doc.objects[i]?.binding === 'title')
  const tags =
    headerObjects.find((object) => object.get('hmId') === 'tags') ??
    headerObjects.find((_, i) => doc.objects[i]?.binding === 'tags')
  const company =
    headerObjects.find((object) => object.get('hmId') === 'company') ??
    headerObjects.find((_, i) => doc.objects[i]?.binding === 'company')
  const tagline = headerObjects.find((object) => object.get('hmId') === 'tagline')
  if (orshotPhoto && tags instanceof F.Textbox) {
    company?.set({ fill: '#ffffff' })
    tags.set({
      text: [values.title, career].filter(Boolean).join(' · ').replace(/\s+/g, ' '),
      left: 48,
      top: layout.headerBottom * 0.65,
      width: 504,
      fill: '#ffffff',
      fontSize: 12,
      fontWeight: 'bold',
      lineHeight: 1,
    })
    tags.initDimensions()
    while (tags.getScaledHeight() > tags.fontSize * 1.5 && tags.fontSize > 9) {
      tags.set({ fontSize: tags.fontSize - 0.5 })
      tags.initDimensions()
    }
    if (title instanceof F.Textbox) {
      title.set({
        text: values.tagline,
        left: 32,
        top: tags.top + tags.getScaledHeight() + 18,
        width: 520,
        fill: '#ffffff',
        fontWeight: 'bold',
        lineHeight: 1.04,
      })
      title.initDimensions()
    }
    tagline?.set({ visible: false })
  }
  if (title instanceof F.Textbox && !doc.originalRender) {
    // '담당자 채 / 용'처럼 어절이 쪼개지지 않게 한다. 폭보다 긴 단어만 글자 단위로 푼다.
    const available = Math.min(title.width, 600 - title.left - 32)
    title.set({
      width: available,
      splitByGrapheme: false,
      ...(doc.source.id?.startsWith('templated:')
        ? { fontSize: Math.min(title.fontSize, 56), lineHeight: 1.15 }
        : {}),
    })
    title.initDimensions()
    if (title.width > available) {
      title.set({ width: available, splitByGrapheme: true })
      title.initDimensions()
    }
  }
  if (!orshotPhoto && title && tags)
    tags.set({ top: Math.max(tags.top, title.top + title.getScaledHeight() + 20) })
  const arranged = [company, title, tags, tagline]
    .filter((node) => node !== undefined)
    .filter((node) => node.visible)
    .sort((a, b) => a.top - b.top)
  arranged.forEach((node, index) => {
    for (const previous of arranged.slice(0, index))
      if (
        node.left < previous.left + previous.getScaledWidth() &&
        previous.left < node.left + node.getScaledWidth()
      )
        node.set({ top: Math.max(node.top, previous.top + previous.getScaledHeight() + 20) })
  })
  const bottom = Math.max(
    layout.headerBottom,
    (tags?.top ?? 0) + (tags?.getScaledHeight() ?? 0) + 24,
    (title?.top ?? 0) + (title?.getScaledHeight() ?? 0) + 32,
    (company?.top ?? 0) + (company?.getScaledHeight() ?? 0) + 32,
    (tagline?.top ?? 0) + (tagline?.getScaledHeight() ?? 0) + 32,
  )
  for (const object of target.getObjects()) {
    if (object.get('hmId') === 'generated-banner' && object instanceof F.FabricImage) {
      const original = object.getOriginalSize()
      const imageWidth = Number(original.width)
      const imageHeight = Number(original.height)
      const scale = Math.max(600 / imageWidth, bottom / imageHeight)
      object.set({
        left: (600 - imageWidth * scale) / 2,
        top: (bottom - imageHeight * scale) / 2,
        width: imageWidth,
        height: imageHeight,
        cropX: 0,
        cropY: 0,
        scaleX: scale,
        scaleY: scale,
        opacity: 1,
        clipPath: new F.Rect({
          left: 0,
          top: 0,
          width: 600,
          height: bottom,
          originX: 'left',
          originY: 'top',
          absolutePositioned: true,
        }),
      })
    }
    if (modern && ['generated-header', 'generated-spine'].includes(String(object.get('hmId')))) {
      object.set({ scaleY: (bottom - object.top) / object.height })
      continue
    }
    if (object.get('hmId') === 'canva-header') {
      object.set({ scaleY: bottom / object.height })
      if (!doc.originalRender && doc.source.id === 'orshot:36661') {
        // 원본에 구워진 짧은 CTA가 보이지 않는 사진 영역만 사용한다.
        object.set({
          scaleY: (bottom / object.height) * 1.38,
          clipPath: new F.Rect({
            left: 0,
            top: 0,
            width: 600,
            height: bottom,
            absolutePositioned: true,
            originX: 'left',
            originY: 'top',
          }),
        })
      }
    }
    if (
      object.type === 'rect' &&
      object.top === 0 &&
      object.getScaledWidth() >= 550 &&
      object.getScaledHeight() > 100
    ) {
      object.set({ scaleY: bottom / object.height })
    }
  }
  const banner = target.getObjects().find((object) => object.get('hmId') === 'generated-banner')
  if (banner) {
    const brand = /^#[0-9a-f]{6}$/i.test(design?.color ?? '')
      ? design!.color
      : (doc.brandColor ?? '#24496c')
    const [red, green, blue] = [1, 3, 5].map((at) =>
      Math.round(Number.parseInt(brand.slice(at, at + 2), 16) * 0.55),
    )
    const tone = `${red},${green},${blue}`
    const shade = rect(0, 0, 600, bottom, 'transparent')
    shade.set({
      hmId: 'generated-banner-shade',
      fill: new F.Gradient({
        type: 'linear',
        gradientUnits: 'percentage',
        coords: { x1: 0, y1: 0, x2: 1, y2: 0 },
        colorStops: [
          { offset: 0, color: `rgba(${tone},0.96)` },
          { offset: 0.65, color: `rgba(${tone},0.8)` },
          { offset: 1, color: `rgba(${tone},0.45)` },
        ],
      }),
    })
    target.moveObjectTo(banner, 1)
    target.moveObjectTo(shade, 2)
    for (const object of [company, title, tags, tagline])
      if (object) object.set({ fill: '#ffffff' })
  }
  if (orshotPhoto) {
    const shade = rect(0, 0, 600, bottom, 'transparent')
    shade.set({
      fill: new F.Gradient({
        type: 'linear',
        gradientUnits: 'percentage',
        coords: { x1: 0, y1: 0, x2: 0, y2: 1 },
        colorStops: [
          { offset: 0, color: 'rgba(0,0,0,0.35)' },
          { offset: 0.32, color: 'rgba(0,0,0,0.05)' },
          { offset: 0.58, color: 'rgba(0,0,0,0.58)' },
          { offset: 1, color: 'rgba(0,0,0,0.9)' },
        ],
      }),
    })
    target.moveObjectTo(shade, 1)
  }
  target.set({ backgroundColor: layout.paper })
  let top = bottom + 28
  let number = 0
  const rendered = new Set<string>()
  for (const row of rows) {
    let rowHeight = 0
    const masonry =
      modern && !planned && row.length > 1 && row.every((section) => section.width < 450)
    const columnBottoms = [top, top]
    for (const item of row) {
      const column = columnBottoms[0] <= columnBottoms[1] ? 0 : 1
      const source = masonry
        ? { ...item, left: margin + (column * (fullWidth + 24)) / 2, width: (fullWidth - 24) / 2 }
        : item
      const sectionY = masonry ? columnBottoms[column] : top
      const periodBand = modern && source.binding === 'period'
      const surface =
        planned && ['TILE', 'QUOTE'].includes(source.variant ?? '')
          ? source.rule
          : periodBand
            ? source.card
            : layout.appearance?.body === 'PANELS' || layout.appearance?.body === 'STRIPES'
              ? layout.appearance.body === 'PANELS' && designed
                ? '#ffffff'
                : number % 2
                  ? layout.paper
                  : '#ffffff'
              : layout.paper
      const section = modern
        ? {
            ...source,
            accent: readable(source.accent, surface),
            heading: { ...source.heading, fill: readable(source.heading.fill, surface) },
            body: { ...source.body, fill: readable(source.body.fill, surface) },
          }
        : source
      const panel = planned
        ? ['TILE', 'QUOTE'].includes(section.variant ?? '')
        : layout.appearance?.body === 'PANELS'
      const stripe = planned
        ? section.variant === 'CHECKLIST'
        : layout.appearance?.body === 'STRIPES'
      const side =
        !planned &&
        layout.appearance?.body === 'SIDEBAR' &&
        (!modern || section.width >= 450) &&
        !['stages', 'documents'].includes(section.binding)
      const inset = panel || periodBand ? (modern ? 18 : designed ? 20 : 14) : 0
      const left = section.left + inset,
        width = section.width - inset * 2
      const sectionTop = sectionY + (modern ? 12 : panel ? 16 : 0)
      const box =
        panel || stripe || periodBand
          ? rect(
              panel || periodBand || planned ? section.left : 0,
              sectionY - 8,
              panel || periodBand || planned ? section.width : doc.width,
              1,
              surface,
            )
          : null
      if (panel && box)
        box.set({
          rx: modern ? 8 : 10,
          ry: modern ? 8 : 10,
          stroke: section.rule,
          strokeWidth: designed ? 0.5 : 1,
        })
      const heading = text(
        labels[section.binding] ?? section.binding,
        left + (section.variant === 'NUMBER' ? 62 : 30),
        sectionTop,
        side ? 92 : width - (section.variant === 'NUMBER' ? 62 : 30),
        {
          ...section.heading,
          ...(side ? { fontSize: Math.min(16, section.heading.fontSize) } : {}),
          fontWeight: 'bold',
          ...(section.variant === 'RIBBON' ? { fill: ink(section.card) } : {}),
          ...(section.variant === 'QUOTE' ? { fontFamily: 'serif' } : {}),
        },
      )
      text(
        String(++number).padStart(2, '0'),
        left,
        sectionTop + 2,
        section.variant === 'NUMBER' ? 56 : 28,
        {
          fontSize: section.variant === 'NUMBER' ? 30 : 11,
          fill: section.variant === 'RIBBON' ? ink(section.card) : section.accent,
          fontWeight: 'normal',
        },
      )
      if (section.variant === 'RIBBON') {
        const ribbon = rect(left - 8, sectionTop - 7, width + 16, heading.height + 14, section.card)
        target.moveObjectTo(ribbon, target.getObjects().indexOf(heading))
      }
      const ruleTop = modern && !panel ? sectionY : sectionTop + heading.height + 10
      if (!side && !['RIBBON', 'NUMBER', 'QUOTE', 'TILE'].includes(section.variant ?? ''))
        rect(
          left,
          ruleTop,
          designed && panel ? 26 : width,
          designed && panel ? 2 : 0.7,
          section.rule,
        )
      const bodyTop = side
        ? sectionTop
        : modern && (!panel || planned)
          ? sectionTop + heading.height + 14
          : ruleTop + (modern ? 14 : designed ? 20 : 16)
      const content = values[section.binding]
      const body = content.startsWith((labels[section.binding] ?? '') + '\n')
        ? content.slice(content.indexOf('\n') + 1)
        : content
      let height = 0
      if (designed && section.binding === 'conditions') {
        const x = side ? left + 142 : left
        const available = side ? width - 142 : width
        const columns = available >= 420 ? 3 : available >= 300 ? 2 : 1
        const gap = 20
        const cellWidth = (available - gap * (columns - 1)) / columns
        const fields = conditions
        for (let offset = 0; offset < fields.length; offset += columns) {
          let rowHeight = 0
          fields.slice(offset, offset + columns).forEach((field, index) => {
            const label = text(
              field.label,
              x + index * (cellWidth + gap),
              bodyTop + height,
              cellWidth,
              {
                ...section.body,
                fontSize: 11,
                fill: '#697583',
                fontWeight: '400',
              },
            )
            const value = text(field.value, label.left, label.top + label.height + 7, cellWidth, {
              ...section.body,
              fontWeight: '600',
            })
            value.set('hmId', 'conditions')
            rowHeight = Math.max(rowHeight, label.height + 7 + value.height + 22)
          })
          height += rowHeight
        }
      } else if (section.binding === 'stages' && design) {
        height = await drawCanvasStages(target, posting, design, left, bodyTop, width, {
          card: section.card,
          final: section.lastCard,
          fontSize: section.body.fontSize,
          variant: layout.appearance?.process,
          paper: layout.paper,
          refined: modern,
        })
      } else if (modern && section.binding === 'documents') {
        height = await drawCanvasDocuments(target, posting.documents, left, bodyTop, width, {
          variant: layout.appearance?.documents ?? 'LIST',
          primary: section.card,
          ink: section.body.fill,
          rule: section.rule,
          paper: surface,
          fontSize: section.body.fontSize,
        })
      } else if (
        section.binding === 'documents' &&
        layout.appearance?.documents &&
        layout.appearance.documents !== 'TILES'
      ) {
        if (layout.appearance.documents === 'COMPACT') {
          rect(left, bodyTop, width, 32, section.card)
          text('제출 서류', left + 10, bodyTop + 7, width * 0.6, {
            ...section.body,
            fontSize: 12,
            fill: ink(section.card),
            fontWeight: 'bold',
          })
          text('형식 · 구분', left + width * 0.7, bodyTop + 7, width * 0.28, {
            ...section.body,
            fontSize: 12,
            fill: ink(section.card),
            fontWeight: 'bold',
          })
          height = 40
        }
        for (const [index, item] of posting.documents.entries()) {
          const name = text(
            `${String(index + 1).padStart(2, '0')}  ${item.label}`,
            left + 8,
            bodyTop + height,
            width * 0.65,
            section.body,
          )
          const meta = text(
            `${item.format} · ${item.required ? '필수' : '선택'}`,
            left + width * 0.7,
            bodyTop + height,
            width * 0.28,
            { ...section.body, fontSize: 12 },
          )
          height += Math.max(name.height, meta.height) + 18
          rect(left, bodyTop + height - 7, width, 1, section.rule)
        }
      } else if (section.binding === 'stages' || section.binding === 'documents') {
        const items =
          section.binding === 'stages'
            ? [...posting.stages.map((s) => s.name), '최종 합격']
            : posting.documents.map(
                (d) => `${d.label}\n${d.format} · ${d.required ? '필수' : '선택'}`,
              )
        const columns =
          section.binding === 'stages'
            ? Math.min(4, items.length)
            : layout.appearance?.documents && layout.appearance.documents !== 'TILES'
              ? 1
              : Math.min(2, items.length)
        const gap = section.binding === 'stages' ? 18 : 12
        const cellWidth = (width - gap * (columns - 1)) / columns
        for (let offset = 0; offset < items.length; offset += columns) {
          const cells = items.slice(offset, offset + columns).map((item, index) => {
            const x = left + index * (cellWidth + gap)
            const node = text(
              `${String(offset + index + 1).padStart(2, '0')}\n${item}`,
              x + 10,
              bodyTop + height + 10,
              cellWidth - 20,
              {
                ...section.body,
                fontSize: Math.max(11, Math.min(14, section.body.fontSize)),
                fontWeight: 'bold',
              },
            )
            return { node, x, final: offset + index === items.length - 1 }
          })
          const cellHeight = Math.max(64, ...cells.map((c) => c.node.height + 20))
          for (const cell of cells) {
            const fill =
              section.binding === 'documents' && layout.appearance?.documents === 'LIST'
                ? layout.paper
                : cell.final && section.binding === 'stages'
                  ? section.lastCard
                  : section.card
            const box = rect(cell.x, bodyTop + height, cellWidth, cellHeight, fill)
            target.moveObjectTo(box, target.getObjects().indexOf(cell.node))
            cell.node.set({ fill: ink(fill) })
          }
          height += cellHeight + 12
        }
      } else if (
        modern &&
        ['duties', 'qualifications', 'preferred', 'benefits', 'notices'].includes(section.binding)
      ) {
        const items =
          section.binding === 'notices'
            ? posting.notices
            : posting.content[
                section.binding as 'duties' | 'qualifications' | 'preferred' | 'benefits'
              ]
        const x = side ? left + 142 : left
        const available = side ? width - 142 : width
        for (const item of items) {
          const node = text(item, x + 12, bodyTop + height, available - 12, section.body)
          rect(x + 1, bodyTop + height + section.body.fontSize * 0.65, 3, 3, section.accent)
          node.set('hmId', section.binding)
          height += node.height + 8
        }
        height = Math.max(0, height - 8)
      } else {
        const node = text(body, left, bodyTop, width, section.body)
        if (side) {
          node.set({ left: left + 142, width: width - 142 })
          node.initDimensions()
        }
        node.set('hmId', section.binding)
        height = node.height
      }
      rendered.add(section.binding)
      let sectionHeight = bodyTop - sectionY + height + 20
      if (side) {
        sectionHeight = Math.max(sectionHeight, heading.height + 24)
        rect(left + 124, sectionY, 2, sectionHeight - 12, section.rule)
      }
      if (stripe) rect(section.left - 16, sectionY, 4, sectionHeight - 8, section.rule)
      rowHeight = Math.max(rowHeight, sectionY - top + sectionHeight)
      box?.set({ height: (modern ? sectionHeight : rowHeight) + 16 })
      if (masonry) columnBottoms[column] = sectionY + sectionHeight + 22
    }
    top += rowHeight + (modern ? 22 : designed ? 36 : 28)
  }
  if (top > 20000 || all.some((key) => values[key] && !rendered.has(key)))
    throw new Error('전체 공고 내용을 안전하게 배치하지 못했어요.')
  target.setDimensions({ height: Math.max(top + 16, bottom + 100) })
  target.getObjects().forEach((node) => node.setCoords())
  for (const node of target.getObjects()) {
    const bounds = node.getBoundingRect()
    if (
      node.type === 'textbox' &&
      (bounds.left < 0 ||
        bounds.left + bounds.width > 601 ||
        bounds.top + bounds.height > target.height)
    )
      throw new Error('글자가 포스터 범위를 벗어나 배치 수정을 해야 해요.')
  }
}
