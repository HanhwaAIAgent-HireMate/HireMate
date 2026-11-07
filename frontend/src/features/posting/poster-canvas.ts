import type { Schemas } from '@/lib/api/client'
import type { StaticCanvas } from 'fabric'
import type { PosterPosting } from '@/features/posting/PostingPoster'
import { conditionRows } from '@/features/posting/conditions'
import { formatDateTime } from '@/lib/format'
import {
  initialPoster,
  posterPalette,
  posterTagline,
  type PosterDesign,
} from '@/features/posting/poster-design'
import { drawCanvasStages } from './poster-canvas-stages'
import type { NativeLayout } from './poster-layout'
import { creativeOrshotColor, creativeOrshotLayout } from './poster-creative-layout'
import { inlinePosterSvg, loadPosterFonts, POSTER_FONT } from './poster-svg'

export type FreeTemplate = NonNullable<Schemas['PosterProposal']['templates']>[number]
export type CanvasObject = Record<string, unknown>
export type PosterCanvas = {
  width: number
  height: number
  brandColor?: string
  heroStyle?: 'PHOTO_CAPTION'
  originalRender?: true
  orshotContentKey?: string
  templatedRegistration?: true
  registeredTemplatedId?: string
  source: { id?: string; name: string; url: string; license: string }
  objects: CanvasObject[]
  nativeLayout?: NativeLayout
  media?: { url: string; height: number; clipHeight: number; version?: number }
  continuation?: { start: number; sampleTop: number; sampleBottom: number; color: string }
  canvaLayout?: {
    version: 2
    headerHeight: number
    paper: string
    ink: string
    accent: string
    columns: number
    logoFrameCleaned?: boolean
    logoCleanupVersion?: number
  }
}

/** 화면과 같은 배치·줄바꿈을 계산한 벡터를 등록해 제공처에서 재배치하지 않도록 한다. */
export async function prepareTemplatedRegistration(posting: PosterPosting, design: PosterDesign) {
  const doc = recolorGeneratedPoster(readPosterCanvas(design.canvasJson!), design.color)
  if (!doc.source.id?.startsWith('generated:') || !doc.nativeLayout)
    throw new Error('새로 생성한 포스터만 등록할 수 있어요.')
  const values = posterBindings(posting, design)
  await loadPosterFonts(Object.values(values).join('\n'))
  const F = await import('fabric')
  const { layoutNativePoster } = await import('./poster-layout')
  const canvas = new F.StaticCanvas(document.createElement('canvas'), {
    width: doc.width,
    height: doc.height,
    backgroundColor: doc.nativeLayout.paper,
  })
  try {
    await canvas.loadFromJSON({ objects: posterCanvasObjects(doc, values, design.color) })
    await layoutNativePoster(canvas, doc, posting, design)
    const height = Math.ceil(canvas.height)
    if (height < 300 || height > 5000) throw new Error('등록 가능한 포스터 길이를 초과했어요.')
    const parsed = new DOMParser().parseFromString(inlinePosterSvg(canvas.toSVG()), 'image/svg+xml')
    parsed.documentElement.setAttribute('width', '600')
    parsed.documentElement.setAttribute('height', String(height))
    parsed.documentElement.setAttribute('viewBox', `0 0 600 ${height}`)
    return {
      sourceId: doc.source.id,
      name: doc.source.name.slice(0, 100),
      svg: new XMLSerializer().serializeToString(parsed.documentElement),
      height,
    }
  } finally {
    await canvas.dispose()
  }
}

export function usesPhotoCaption(doc: PosterCanvas): boolean {
  return (
    !doc.originalRender &&
    doc.source.url === 'https://orshot.com/templates/' &&
    (doc.heroStyle === 'PHOTO_CAPTION' || doc.source.id === 'orshot:36661')
  )
}

/** 생성 테마의 배경·본문·강조색을 함께 바꾼다. 원본 캔버스는 저장된 기준 배색으로 남긴다. */
export function recolorGeneratedPoster(doc: PosterCanvas, color: string): PosterCanvas {
  if (
    doc.source.url !== 'hiremate:generated' ||
    !doc.brandColor ||
    doc.brandColor.toLowerCase() === color.toLowerCase()
  )
    return doc
  const hsl = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((at) => Number.parseInt(hex.slice(at, at + 2), 16) / 255)
    const max = Math.max(r, g, b),
      min = Math.min(r, g, b),
      delta = max - min,
      l = (max + min) / 2
    const h =
      delta === 0
        ? 0
        : max === r
          ? ((g - b) / delta) % 6
          : max === g
            ? (b - r) / delta + 2
            : (r - g) / delta + 4
    return { h: (h * 60 + 360) % 360, s: delta === 0 ? 0 : delta / (1 - Math.abs(2 * l - 1)), l }
  }
  const toHex = (h: number, s: number, l: number) => {
    const c = (1 - Math.abs(2 * l - 1)) * s,
      x = c * (1 - Math.abs(((h / 60) % 2) - 1)),
      m = l - c / 2
    const rgb =
      h < 60
        ? [c, x, 0]
        : h < 120
          ? [x, c, 0]
          : h < 180
            ? [0, c, x]
            : h < 240
              ? [0, x, c]
              : h < 300
                ? [x, 0, c]
                : [c, 0, x]
    return (
      '#' +
      rgb
        .map((value) =>
          Math.round((value + m) * 255)
            .toString(16)
            .padStart(2, '0'),
        )
        .join('')
    )
  }
  const hue = hsl(color).h
  const shift = (value: unknown): unknown => {
    if (typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)) {
      if (
        value.toLowerCase() === doc.brandColor!.toLowerCase() ||
        value.toLowerCase() === color.toLowerCase()
      )
        return color
      const tone = hsl(value)
      return tone.s < 0.12 || tone.l < 0.2 ? value : toHex(hue, tone.s, tone.l)
    }
    if (Array.isArray(value)) return value.map(shift)
    if (value && typeof value === 'object')
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, shift(item)]))
    return value
  }
  const changed = shift(doc) as PosterCanvas
  changed.brandColor = color
  if (changed.nativeLayout) {
    const paper =
      '#' +
      [1, 3, 5]
        .map((at) =>
          Math.round(Number.parseInt(color.slice(at, at + 2), 16) * 0.04 + 255 * 0.96)
            .toString(16)
            .padStart(2, '0'),
        )
        .join('')
    changed.nativeLayout.paper = paper
    doc.objects.forEach((object, index) => {
      if (object.fill === doc.nativeLayout?.paper) changed.objects[index].fill = paper
    })
    const background = changed.objects.find((object) => object.hmId === 'generated-header')?.fill
    const ink =
      typeof background === 'string' && contrast('#ffffff', background) >= 4.5
        ? '#ffffff'
        : '#101820'
    changed.objects.forEach((object) => {
      if (['company', 'title', 'tagline', 'tags'].includes(String(object.binding)))
        object.fill = ink
    })
  }
  return changed
}

export function nextExternalTemplateName(names: string[], prefix = '외부템플릿'): string {
  const used = new Set(names)
  let index = 1
  while (used.has(`${prefix}${index}`)) index++
  return `${prefix}${index}`
}

/** 흰색을 충분히 섞어 원본 로고의 진한 글자와 심벌이 읽히는 받침색을 만든다. */
export function posterLogoSurface(background = '#ffffff'): string {
  const rgb = [1, 3, 5].map((at) => Number.parseInt(background.slice(at, at + 2), 16))
  if (rgb.some((value) => !Number.isFinite(value))) return '#ffffff'
  const light = rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722
  if (light > 235) return '#ffffff'
  return `#${rgb
    .map((value) =>
      Math.round(value * 0.08 + 255 * 0.92)
        .toString(16)
        .padStart(2, '0'),
    )
    .join('')}`
}

/** 알파나 글자 윤곽은 제거하지 않고 흰 바탕만 부드럽게 받침색에 맞춘다. */
export function preparePosterLogo(
  canvas: HTMLCanvasElement,
  background = '#ffffff',
): HTMLCanvasElement {
  const context = canvas.getContext('2d')
  if (!context) return canvas
  const surface = posterLogoSurface(background)
  const rgb = [1, 3, 5].map((at) => Number.parseInt(surface.slice(at, at + 2), 16))
  const image = context.getImageData(0, 0, canvas.width, canvas.height)
  let left = canvas.width,
    top = canvas.height,
    right = -1,
    bottom = -1
  for (let at = 0; at < image.data.length; at += 4) {
    const alpha = image.data[at + 3] / 255
    const minimum = Math.min(image.data[at], image.data[at + 1], image.data[at + 2])
    const maximum = Math.max(image.data[at], image.data[at + 1], image.data[at + 2])
    if (alpha > 0.06 && (minimum < 230 || maximum - minimum > 24)) {
      const x = (at / 4) % canvas.width,
        y = Math.floor(at / 4 / canvas.width)
      left = Math.min(left, x)
      right = Math.max(right, x)
      top = Math.min(top, y)
      bottom = Math.max(bottom, y)
    }
    const strength = Math.max(
      0,
      (Math.min(image.data[at], image.data[at + 1], image.data[at + 2]) - 180) / 75,
    )
    for (let channel = 0; channel < 3; channel++) {
      const original = image.data[at + channel]
      const softened = original + (rgb[channel] - 255) * strength
      image.data[at + channel] = Math.round(softened * alpha + rgb[channel] * (1 - alpha))
    }
    image.data[at + 3] = 255
  }
  context.putImageData(image, 0, 0)
  if (right < left) return canvas
  const padding = Math.max(1, Math.ceil(Math.min(canvas.width, canvas.height) * 0.025))
  left = Math.max(0, left - padding)
  top = Math.max(0, top - padding)
  right = Math.min(canvas.width - 1, right + padding)
  bottom = Math.min(canvas.height - 1, bottom + padding)
  const cropped = document.createElement('canvas')
  cropped.width = right - left + 1
  cropped.height = bottom - top + 1
  cropped
    .getContext('2d')
    ?.drawImage(
      canvas,
      left,
      top,
      cropped.width,
      cropped.height,
      0,
      0,
      cropped.width,
      cropped.height,
    )
  return cropped
}

/** 예전 양식에 이미지로 구워진 상단 오른쪽의 빈 로고 테두리를 찾아 주변 배경으로 잇는다. */
export function clearCanvaLogoPlaceholder(canvas: HTMLCanvasElement): boolean {
  const context = canvas.getContext('2d')
  if (!context) return false
  const { width, height } = canvas
  const image = context.getImageData(0, 0, width, height)
  const data = image.data
  const x0 = Math.floor(width * 0.72),
    x1 = Math.floor(width * 0.97)
  const y0 = Math.floor(height * 0.01),
    y1 = Math.floor(Math.min(height * 0.16, width * 0.24))
  const lines: { y: number; left: number; right: number }[] = []
  const difference = (at: number, reference: number) =>
    Math.max(...[0, 1, 2].map((c) => data[at + c] - data[reference + c]))
  for (let y = y0; y < y1; y++) {
    const reference = (y * width + Math.floor(width * 0.7)) * 4
    let left = -1,
      bestLeft = -1,
      bestRight = -1
    for (let x = x0; x <= x1; x++) {
      const bright = x < x1 && difference((y * width + x) * 4, reference) > 20
      if (bright && left < 0) left = x
      if (!bright && left >= 0) {
        if (x - left > bestRight - bestLeft) {
          bestLeft = left
          bestRight = x
        }
        left = -1
      }
    }
    if (bestRight - bestLeft > width * 0.09) lines.push({ y, left: bestLeft, right: bestRight })
  }
  let first = lines[0],
    last = lines.at(-1)
  if (
    !first ||
    !last ||
    last.y - first.y < width * 0.04 ||
    last.y - first.y > width * 0.18 ||
    Math.abs(first.left - last.left) > width * 0.025 ||
    Math.abs(first.right - last.right) > width * 0.025
  ) {
    // 일부만 남은 세로 테두리도 검사한다. 로고가 놓이는 상단 오른쪽 범위에만 적용한다.
    let found = false
    for (let x = x0; x < x1 && !found; x++) {
      let run = 0
      for (let y = y0; y < y1; y++) {
        const reference = (y * width + Math.floor(width * 0.7)) * 4
        run = difference((y * width + x) * 4, reference) > 18 ? run + 1 : 0
        if (run > width * 0.04) {
          found = true
          break
        }
      }
    }
    if (!found) return false
    first = { y: y0, left: x0, right: x1 }
    last = { y: y1 - 1, left: x0, right: x1 }
  }
  const margin = Math.max(12, Math.ceil(width * 0.025))
  const left = Math.max(x0, Math.min(first.left, last.left) - margin)
  const right = Math.min(width, Math.max(first.right, last.right) + margin)
  for (let y = Math.max(0, first.y - margin); y < Math.min(height, last.y + margin + 1); y++) {
    const reference = (y * width + left - 8) * 4
    for (let x = left; x < right; x++)
      for (let c = 0; c < 3; c++) data[(y * width + x) * 4 + c] = data[reference + c]
  }
  context.putImageData(image, 0, 0)
  return true
}
export function samePosterCanvas(first?: string | null, second?: string | null): boolean {
  if (!first || !second) return false
  try {
    const a = readPosterCanvas(first).source
    const b = readPosterCanvas(second).source
    return a.id && b.id ? a.id === b.id : a.name === b.name
  } catch {
    return false
  }
}

export function sameImportedArtwork(first: string | null | undefined, second: string): boolean {
  if (!first) return false
  try {
    const { source: left, ...firstArtwork } = readPosterCanvas(first)
    const { source: right, ...secondArtwork } = readPosterCanvas(second)
    return (
      left.url !== 'hiremate:generated' &&
      right.url !== 'hiremate:generated' &&
      JSON.stringify(firstArtwork) === JSON.stringify(secondArtwork)
    )
  } catch {
    return false
  }
}

export function posterAfterTemplateDeletion(
  current: Schemas['PosterDesign'],
  deleted: Schemas['PosterBrand']['templates'][number],
  brand: Schemas['PosterBrand'],
): Schemas['PosterDesign'] {
  const selected = deleted.canvasJson
    ? samePosterCanvas(current.canvasJson, deleted.canvasJson)
    : !current.canvasJson &&
      current.template === deleted.template &&
      current.color === deleted.color &&
      current.decoration === deleted.decoration
  if (!selected) return current
  return {
    ...initialPoster(brand),
    enabled: current.enabled,
    showLogo: current.showLogo,
    logoFileId: current.logoFileId,
    stageIcons: current.stageIcons,
  }
}

/** 현재 공고를 채우되 Fabric 7의 중앙 원점으로 저장했던 초기 데이터도 복구한다. */
export function posterCanvasObjects(
  doc: PosterCanvas,
  values: Record<string, string>,
  color: string,
): CanvasObject[] {
  const oldPalette = posterPalette(doc.brandColor ?? color) as Record<string, string>
  const palette = posterPalette(color) as Record<string, string>
  const colors = new Map(
    Object.entries(oldPalette)
      .filter(([key]) => key !== '--poster-on-primary')
      .map(([key, value]) => [value, palette[key]]),
  )
  const recolor = (value: unknown): unknown => {
    if (typeof value === 'string') return colors.get(value) ?? value
    if (Array.isArray(value)) return value.map(recolor)
    if (value && typeof value === 'object')
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, recolor(item)]))
    return value
  }
  const objects = doc.objects.map((original) => {
    const element = recolor(original) as CanvasObject
    if (
      ['text', 'i-text', 'textbox'].includes(String(element.type).toLowerCase()) &&
      element.fontFamily !== 'serif'
    )
      element.fontFamily = POSTER_FONT
    const binding = typeof element.binding === 'string' ? element.binding : null
    if (!binding) return element
    if (
      ['company', 'title', 'tags', 'tagline'].includes(binding) &&
      original.fill === oldPalette['--poster-on-primary']
    )
      element.fill = palette['--poster-on-primary']
    const left = Math.min(Math.max(24, Number(element.left) || 40), doc.width - 44)
    return {
      ...element,
      originX: 'left',
      originY: 'top',
      splitByGrapheme: true,
      left,
      width: Math.max(20, Math.min(Number(element.width) || doc.width - 80, doc.width - left - 24)),
      text: values[binding] ?? '',
    }
  })
  return objects.map((element, index) => {
    if (typeof element.binding !== 'string') return element
    if (doc.canvaLayout || doc.nativeLayout) return element
    const x = Number(element.left) + Number(element.width) / 2
    const y = Number(element.top) + Number(element.fontSize ?? 14) / 2
    const backdrop = objects
      .slice(0, index)
      .reverse()
      .find(
        (shape) =>
          shape.type?.toString().toLowerCase() === 'rect' &&
          x >= Number(shape.left ?? 0) &&
          x <= Number(shape.left ?? 0) + Number(shape.width) * Number(shape.scaleX ?? 1) &&
          y >= Number(shape.top ?? 0) &&
          y <= Number(shape.top ?? 0) + Number(shape.height) * Number(shape.scaleY ?? 1),
      )
    const background = typeof backdrop?.fill === 'string' ? backdrop.fill : '#ffffff'
    const fill = typeof element.fill === 'string' ? element.fill : '#24313e'
    if (contrast(fill, background) >= 4.5) return element
    const readable =
      contrast('#ffffff', background) > contrast('#24313e', background) ? '#ffffff' : '#24313e'
    return { ...element, fill: readable }
  })
}

function contrast(first: string, second: string): number {
  const luminance = (value: string) => {
    if (!/^#[0-9a-f]{6}$/i.test(value)) return null
    const rgb = [1, 3, 5].map((offset) => {
      const channel = Number.parseInt(value.slice(offset, offset + 2), 16) / 255
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    })
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722
  }
  const a = luminance(first)
  const b = luminance(second)
  return a === null || b === null ? 21 : (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

const TYPES = new Set([
  'rect',
  'circle',
  'ellipse',
  'line',
  'polyline',
  'polygon',
  'path',
  'text',
  'textbox',
  'group',
  'image',
])
const FORBIDDEN = new Set([
  '__proto__',
  'constructor',
  'prototype',
  'src',
  'href',
  'filters',
  'clipPath',
  'backgroundImage',
  'overlayImage',
])

export function readPosterCanvas(value: string): PosterCanvas {
  if (value.length > 200000) throw new Error('포스터 데이터가 너무 커요.')
  const data: unknown = JSON.parse(value)
  if (!data || typeof data !== 'object') throw new Error('포스터 형식을 확인하지 못했어요.')
  const doc = data as Record<string, unknown>
  if (
    typeof doc.width !== 'number' ||
    doc.width < 300 ||
    doc.width > 1600 ||
    typeof doc.height !== 'number' ||
    doc.height < 300 ||
    doc.height > 20000 ||
    !Array.isArray(doc.objects) ||
    doc.objects.length > 150
  )
    throw new Error('지원하지 않는 포스터 크기예요.')
  let count = 0
  const check = (item: unknown): void => {
    if (!item || typeof item !== 'object') return
    if (++count > 10000) throw new Error('포스터 요소가 너무 많아요.')
    for (const [key, val] of Object.entries(item)) {
      if (
        key === 'src' &&
        (item as CanvasObject).type === 'Image' &&
        typeof val === 'string' &&
        /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(val) &&
        val.length <= 160000
      )
        continue
      if (FORBIDDEN.has(key)) throw new Error('외부 실행 요소는 가져올 수 없어요.')
      if (key === 'type' && typeof val === 'string' && !TYPES.has(val.toLowerCase()))
        throw new Error('지원하지 않는 요소예요.')
      if (typeof val === 'number' && (!Number.isFinite(val) || Math.abs(val) > 100000))
        throw new Error('요소 크기를 확인해 주세요.')
      if (typeof val === 'object') check(val)
    }
  }
  check(doc.objects)
  const source = doc.source as Record<string, unknown> | undefined
  if (doc.continuation) {
    const theme = doc.continuation as Record<string, unknown>
    if (
      typeof theme.start !== 'number' ||
      typeof theme.sampleTop !== 'number' ||
      typeof theme.sampleBottom !== 'number' ||
      !Number.isFinite(theme.start) ||
      !Number.isFinite(theme.sampleTop) ||
      !Number.isFinite(theme.sampleBottom) ||
      theme.start < 300 ||
      theme.start > doc.height ||
      theme.sampleTop < 0 ||
      theme.sampleTop >= theme.sampleBottom ||
      theme.sampleBottom > theme.start ||
      typeof theme.color !== 'string' ||
      !/^#[0-9a-f]{6}$/i.test(theme.color)
    )
      throw new Error('이어지는 배경 영역을 확인하지 못했어요.')
  }
  if (doc.canvaLayout) {
    const layout = doc.canvaLayout as Record<string, unknown>
    if (
      layout.version !== 2 ||
      typeof layout.headerHeight !== 'number' ||
      !Number.isFinite(layout.headerHeight) ||
      layout.headerHeight < 200 ||
      layout.headerHeight > 1500 ||
      ![1, 2].includes(Number(layout.columns)) ||
      !['paper', 'ink', 'accent'].every(
        (key) => typeof layout[key] === 'string' && /^#[0-9a-f]{6}$/i.test(layout[key]),
      )
    )
      throw new Error('Canva 본문 구성을 확인하지 못했어요.')
  }
  if (doc.nativeLayout) {
    const layout = doc.nativeLayout as NativeLayout
    if (
      layout.version !== 1 ||
      (layout.sourceTemplate !== undefined && !creativeOrshotColor(layout.sourceTemplate)) ||
      !/^#[0-9a-f]{6}$/i.test(layout.paper) ||
      !Number.isFinite(layout.headerBottom) ||
      layout.headerBottom < 0 ||
      layout.headerBottom > 3000 ||
      !Array.isArray(layout.sections) ||
      layout.sections.length > 13
    )
      throw new Error('원본 레이아웃 정보를 확인하지 못했어요.')
    for (const section of layout.sections) {
      if (
        ![
          'intro',
          'conditions',
          'duties',
          'qualifications',
          'preferred',
          'benefits',
          'stages',
          'documents',
          'notices',
          'period',
        ].includes(section.binding) ||
        ![section.left, section.top, section.width, section.height].every(
          (n) => Number.isFinite(n) && n >= 0 && n <= 20000,
        ) ||
        section.left + section.width > 601 ||
        ![
          section.accent,
          section.rule,
          section.card,
          section.lastCard,
          section.cardInk,
          section.heading.fill,
          section.body.fill,
        ].every((c) => /^#[0-9a-f]{6}$/i.test(c)) ||
        ![section.heading.fontSize, section.body.fontSize].every(
          (n) => Number.isFinite(n) && n >= 8 && n <= 120,
        )
      )
        throw new Error('원본 구역의 크기나 배색을 확인하지 못했어요.')
    }
  }
  const media = doc.media as Partial<NonNullable<PosterCanvas['media']>> | undefined
  if (
    media &&
    (source?.url !== 'https://orshot.com/templates/' ||
      typeof media.url !== 'string' ||
      !/^https:\/\/storage\.orshot\.com\/[A-Za-z0-9_./-]+\.mp4$/.test(media.url) ||
      typeof media.height !== 'number' ||
      !Number.isFinite(media.height) ||
      media.height < 10 ||
      media.height > 20000 ||
      typeof media.clipHeight !== 'number' ||
      !Number.isFinite(media.clipHeight) ||
      media.clipHeight < 260 ||
      media.clipHeight > (doc.originalRender === true ? 3000 : 480))
  )
    throw new Error('원본 영상 정보를 확인하지 못했어요.')
  if (
    !source ||
    typeof source.name !== 'string' ||
    !(
      (source.url === 'https://inkscape.de/vorlagen/' && source.license === 'CC0 1.0') ||
      (source.url === 'https://www.canva.com/' && source.license === 'Canva 계정 디자인') ||
      (source.url === 'hiremate:generated' &&
        source.license === 'AI 생성' &&
        typeof source.id === 'string' &&
        /^generated:[a-f0-9-]{36}$/.test(source.id)) ||
      (source.url === 'https://templated.io/templates/' && source.license === 'Templated 테마') ||
      (source.url === 'https://orshot.com/templates/' &&
        source.license === 'Orshot 계정 디자인' &&
        typeof source.id === 'string' &&
        /^orshot:[1-9][0-9]*$/.test(source.id))
    )
  ) {
    throw new Error('무료 템플릿 출처를 확인하지 못했어요.')
  }
  return data as PosterCanvas
}

export function posterBindings(
  posting: PosterPosting,
  design?: PosterDesign,
): Record<string, string> {
  const { content } = posting
  const lines = (title: string, values: string[]) =>
    values.length ? `${title}\n${values.map((value) => `• ${value}`).join('\n')}` : ''
  return {
    company: posting.companyName,
    title: content.title || '채용 공고',
    tagline: posterTagline(posting, design),
    tags: [content.jobCategory, content.employmentType, content.career, content.location]
      .filter(Boolean)
      .join(' · '),
    intro: content.intro ? `회사 소개\n${content.intro}` : '',
    conditions: conditionRows(content)
      .map((row) => `${row.label}  ${row.value}`)
      .join('\n'),
    duties: lines('주요 업무', content.duties),
    qualifications: lines('자격 요건', content.qualifications),
    preferred: lines('우대 사항', content.preferred),
    benefits: lines('복지 및 혜택', content.benefits),
    stages: posting.stages.length
      ? `전형 절차\n${[...posting.stages.map((stage) => stage.name), '최종 합격'].join(' → ')}`
      : '',
    documents: lines(
      '제출 서류',
      posting.documents.map(
        (item) => `${item.label} ${item.format} · ${item.required ? '필수' : '선택'}`,
      ),
    ),
    notices: lines('유의사항', posting.notices),
    period:
      posting.openAt && posting.closeAt
        ? `접수 기간\n${formatDateTime(posting.openAt)} ~ ${formatDateTime(posting.closeAt)}`
        : '',
  }
}

export async function importPosterTemplate(
  template: FreeTemplate,
  posting: PosterPosting,
  color: string,
): Promise<string> {
  const F = await import('fabric')
  await document.fonts.ready
  const parsed = new DOMParser().parseFromString(template.svg, 'image/svg+xml')
  if (parsed.querySelector('parsererror, script, foreignObject, image, style, use'))
    throw new Error('지원하지 않는 SVG 요소가 있어요.')
  if (
    [...parsed.querySelectorAll('*')].some((element) =>
      [...element.attributes].some((attr) => /^on|href|src/i.test(attr.name)),
    )
  )
    throw new Error('외부 참조가 있는 SVG는 가져올 수 없어요.')
  if (template.id.startsWith('templated:')) {
    if (
      template.sourceUrl !== 'https://templated.io/templates/' ||
      template.license !== 'Templated 테마'
    )
      throw new Error('Templated 출처를 확인하지 못했어요.')
    return importTemplatedTheme(template, parsed, posting, color)
  }
  const imported = await F.loadSVGFromString(template.svg)
  const values = posterBindings(posting)
  const objects: CanvasObject[] = []
  const palette = posterPalette(color) as Record<string, string>
  const band = template.id === 'inkscape-a4'
  const light = template.id === 'inkscape-a5'
  const names: Record<string, string> = {
    'inkscape-frame': '프레임 채용형',
    'inkscape-a4': '라인 채용형',
    'inkscape-a5': '밴드 채용형',
  }
  let y = 48
  const text = (binding: string, left: number, top: number, width: number, fontSize = 15) => {
    const header = ['company', 'title', 'tags'].includes(binding)
    const node = new F.Textbox(values[binding], {
      left,
      top,
      originX: 'left',
      originY: 'top',
      splitByGrapheme: true,
      width,
      fontSize,
      fontFamily: POSTER_FONT,
      fill: header && band ? palette['--poster-on-primary'] : '#24313e',
      lineHeight: 1.6,
      fontWeight: ['company', 'title'].includes(binding) ? 'bold' : 'normal',
      styles:
        !header && binding !== 'conditions'
          ? {
              0: Object.fromEntries(
                [...values[binding].split('\n')[0]].map((_, index) => [
                  index,
                  { fontWeight: 'bold', fill: palette['--poster-heading'] },
                ]),
              ),
            }
          : {},
    })
    const serialized: CanvasObject = { ...node.toObject() }
    // 문구는 저장하지 않는다. 그릴 때 항상 최신 공고에서 다시 채운다.
    objects.push({ ...serialized, text: '', hmId: binding, binding })
    return node.height
  }
  for (const [binding, size] of [
    ['company', 20],
    ['title', 34],
    ['tags', 13],
  ] as const) {
    if (values[binding]) y += text(binding, 40, y, 520, size) + 24
  }
  const heroHeight = y + 12
  y += 48
  for (const binding of ['intro', 'conditions']) {
    if (values[binding]) y += text(binding, 40, y, 520, 14) + 32
  }
  for (const pair of [
    ['duties', 'qualifications'],
    ['preferred', 'benefits'],
  ]) {
    const active = pair.filter((key) => values[key])
    let height = 0
    active.forEach((binding, index) => {
      height = Math.max(height, text(binding, 40 + index * 274, y, active.length === 2 ? 246 : 520))
    })
    if (active.length) y += height + 32
  }
  for (const binding of ['stages', 'documents', 'notices', 'period']) {
    if (values[binding]) y += text(binding, 40, y, 520, 14) + 28
  }
  const height = Math.max(850, Math.ceil(y + 32))
  const sourceWidth = Number(imported.options.width) || 600
  const sourceHeight = Number(imported.options.height) || 850
  const decoration = imported.objects
    .filter((item) => item && !['text', 'textbox', 'i-text'].includes(item.type.toLowerCase()))
    // 기본 문서 SVG의 입력 칸·구획선은 새 공고의 행 위치와 맞지 않는다.
    // 종이 배경만 보존하고 구획은 아래의 실측된 공고 레이아웃에서 만든다.
    .filter(
      (item) =>
        item &&
        item.type.toLowerCase() === 'rect' &&
        !item.stroke &&
        item.width * item.scaleX >= sourceWidth * 0.9 &&
        item.height * item.scaleY >= sourceHeight * 0.9,
    )
    .map((item, index) => {
      if (!item) throw new Error('SVG 요소를 읽지 못했어요.')
      item.set({
        left: (item.left * 600) / sourceWidth,
        top: (item.top * height) / sourceHeight,
        scaleX: (item.scaleX * 600) / sourceWidth,
        scaleY: (item.scaleY * height) / sourceHeight,
      })
      return { ...(item.toObject() as CanvasObject), hmId: `decoration-${index}` }
    })
  const shape = (node: InstanceType<typeof F.Rect>, id: string) => ({
    ...node.toObject(),
    hmId: id,
  })
  const accents = [
    shape(
      new F.Rect({
        left: 24,
        top: 24,
        width: band || light ? 552 : 4,
        height: heroHeight - 24,
        originX: 'left',
        originY: 'top',
        fill: band ? color : light ? palette['--poster-soft'] : color,
      }),
      'hero-accent',
    ),
    shape(
      new F.Rect({
        left: 40,
        top: heroHeight + 12,
        width: 520,
        height: 2,
        originX: 'left',
        originY: 'top',
        fill: color,
      }),
      'hero-rule',
    ),
  ]
  const result = JSON.stringify({
    width: 600,
    brandColor: color,
    height,
    source: {
      id: template.id,
      name: names[template.id] ?? template.name,
      url: template.sourceUrl,
      license: template.license,
    },
    objects: [...decoration, ...accents, ...objects],
  })
  readPosterCanvas(result)
  return result
}

/** Canva의 상단 이미지는 보존하고 본문은 공고 길이에 맞는 같은 테마의 행으로 재구성한다. */
async function importTemplatedTheme(
  template: FreeTemplate,
  parsed: Document,
  posting: PosterPosting,
  color: string,
): Promise<string> {
  const F = await import('fabric')
  const root = parsed.documentElement
  const width = Number(root.getAttribute('width'))
  const height = Number(root.getAttribute('height'))
  const bodyTop = Number(root.getAttribute('data-body-top'))
  if (
    width < 300 ||
    width > 5000 ||
    height < width ||
    height > 5000 ||
    !Number.isFinite(bodyTop) ||
    bodyTop < 100 ||
    bodyTop > height * 0.7
  )
    throw new Error('외부 테마 크기를 확인하지 못했어요.')
  // 원본 예시 문구는 저장·렌더링하지 않는다. 테마의 벡터 배경만 읽는다.
  parsed.querySelectorAll('text, tspan, title, desc').forEach((node) => node.remove())
  const loaded = await F.loadSVGFromString(new XMLSerializer().serializeToString(root))
  const target = new F.StaticCanvas(document.createElement('canvas'), { width, height })
  try {
    target.add(...loaded.objects.filter((node) => node !== null))
    const background = target.toDataURL({
      format: 'jpeg',
      quality: 0.8,
      multiplier: Math.min(1, 600 / width),
    })
    const regions = [
      { id: 'left', text: '', left: 40, top: bodyTop + 20, width: width * 0.4, height: 100 },
      {
        id: 'right',
        text: '',
        left: width * 0.55,
        top: bodyTop + 20,
        width: width * 0.4,
        height: 100,
      },
    ]
    const result = await importCanvaPoster(
      {
        template: {
          id: template.id,
          name: template.name,
          editUrl: template.sourceUrl,
          background,
          width,
          height,
          regions,
        },
        mapping: {
          bindings: [
            { elementId: 'left', binding: 'duties' },
            { elementId: 'right', binding: 'qualifications' },
          ],
        },
      },
      posting,
      color,
    )
    const doc = readPosterCanvas(result)
    doc.source = {
      id: template.id,
      name: template.name,
      url: template.sourceUrl,
      license: template.license,
    }
    const encoded = JSON.stringify(doc)
    readPosterCanvas(encoded)
    return encoded
  } finally {
    await target.dispose()
  }
}

/** Orshot은 원본의 글을 제거한 상단 배경을 보존하고 편집 가능한 본문을 같은 색조로 확장한다. */
export async function importOrshotPoster(
  template: Schemas['OrshotTemplate'],
  color: string,
  originalRender = false,
  posting?: PosterPosting,
): Promise<string> {
  if (
    !/^orshot:[1-9][0-9]*$/.test(template.id) ||
    !/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(template.background) ||
    template.background.length > 160000 ||
    template.width !== 600 ||
    template.height < (originalRender ? 30 : 260) ||
    template.height > (originalRender ? 3000 : 480)
  )
    throw new Error('Orshot 원본 배경을 확인하지 못했어요.')
  const F = await import('fabric')
  const image = await F.FabricImage.fromURL(template.background)
  const pixels = image.toCanvasElement().getContext('2d')
  const sample = pixels?.getImageData(
    Math.min(36, image.width - 1),
    Math.min(36, image.height - 1),
    1,
    1,
  ).data
  const ink =
    sample && sample[0] * 0.2126 + sample[1] * 0.7152 + sample[2] * 0.0722 > 150
      ? '#24313e'
      : '#ffffff'
  if (originalRender && pixels) {
    color =
      creativeOrshotColor(template.layoutStyle) ??
      orshotArtworkColor(pixels.getImageData(0, 0, image.width, image.height).data, color)
  }
  const palette = posterPalette(color) as Record<string, string>
  const [red, green, blue] = [1, 3, 5].map((at) => Number.parseInt(color.slice(at, at + 2), 16))
  const graphic = blue > green * 1.2 && red > green * 1.2
  const warm = red > blue * 1.3
  const objects: CanvasObject[] = [
    {
      type: 'Image',
      hmId: 'canva-header',
      src: template.background,
      left: 0,
      top: 0,
      width: template.width,
      height: template.height,
      originX: 'left',
      originY: 'top',
    },
  ]
  const text = (binding: string, top: number, size: number, width = 520) =>
    objects.push({
      type: 'Textbox',
      hmId: binding,
      binding,
      text: '',
      left: 40,
      top,
      width,
      fontSize: size,
      fontFamily: POSTER_FONT,
      fill: ink,
      fontWeight: binding === 'title' ? 'bold' : 'normal',
      originX: 'left',
      originY: 'top',
      splitByGrapheme: true,
    })
  if (!originalRender) {
    text('company', 28, 17, 350)
    text('tagline', 82, 13)
    text('title', 122, 38)
    text('tags', Math.max(220, template.height - 70), 13)
  }
  const sections = [
    'intro',
    'conditions',
    'duties',
    'qualifications',
    'preferred',
    'benefits',
    'stages',
    'documents',
    'notices',
    'period',
  ].map((binding, index) => ({
    binding,
    left: ['qualifications', 'benefits'].includes(binding) ? 312 : 40,
    top: template.height + 40 + index * 140,
    width: ['duties', 'qualifications', 'preferred', 'benefits'].includes(binding) ? 248 : 520,
    height: 120,
    heading: { fontSize: 18, fill: palette['--poster-heading'], fontWeight: 'bold' },
    body: { fontSize: 14, fill: '#24313e', fontWeight: 'normal' },
    accent: color,
    rule: `#${new F.Color(palette['--poster-line']).toHex()}`,
    card: `#${new F.Color(palette['--poster-soft']).toHex()}`,
    lastCard: color,
    cardInk: palette['--poster-on-primary'],
  }))
  sections.find((s) => s.binding === 'qualifications')!.top = sections.find(
    (s) => s.binding === 'duties',
  )!.top
  sections.find((s) => s.binding === 'benefits')!.top = sections.find(
    (s) => s.binding === 'preferred',
  )!.top
  const result = JSON.stringify({
    width: 600,
    height: template.height + 1600,
    brandColor: color,
    source: {
      id: template.id,
      name: template.name,
      url: 'https://orshot.com/templates/',
      license: 'Orshot 계정 디자인',
    },
    ...(originalRender ? { originalRender: true } : {}),
    ...(posting ? { orshotContentKey: orshotPostingKey(posting) } : {}),
    ...(!originalRender && /\bphoto hero\b/i.test(template.name)
      ? { heroStyle: 'PHOTO_CAPTION' }
      : {}),
    ...(template.motionUrl
      ? {
          media: {
            url: template.motionUrl,
            height: template.motionHeight,
            clipHeight: template.height,
            version: 2,
          },
        }
      : {}),
    objects,
    nativeLayout: creativeOrshotLayout(template.layoutStyle, {
      version: 1,
      paper: '#ffffff',
      headerBottom: template.height,
      sections,
      appearance: {
        edition: 3,
        body: graphic ? 'PANELS' : 'EDITORIAL',
        process: graphic ? 'CARDS' : warm ? 'STEPS' : 'TIMELINE',
        documents: graphic ? 'COMPACT' : warm ? 'LIST' : 'TILES',
        expression: 'CALM',
      },
    }),
  } satisfies PosterCanvas)
  readPosterCanvas(result)
  return result
}

/** 원본 영상에 구워지는 문구가 바뀔 때만 다시 렌더링한다. 본문은 매번 현재 공고로 그린다. */
export function orshotPostingKey(posting: PosterPosting): string {
  const content = JSON.stringify([
    5,
    posting.companyName,
    posting.content.title,
    posting.content.career,
    posting.content.employmentType,
    posting.content.location,
  ])
  let first = 2166136261
  let second = 5381
  for (let at = 0; at < content.length; at++) {
    first = Math.imul(first ^ content.charCodeAt(at), 16777619)
    second = Math.imul(second, 33) ^ content.charCodeAt(at)
  }
  return `source-layout-v2-${(first >>> 0).toString(16)}-${(second >>> 0).toString(16)}`
}

/** 새 헤더와 원본 영상만 교체하고 HR이 고른 본문 배치와 배색은 보존한다. */
export function refreshOrshotCanvas(current: string, refreshed: string): string {
  const original = readPosterCanvas(current)
  const next = readPosterCanvas(refreshed)
  if (!original.source.id?.startsWith('orshot:') || original.source.id !== next.source.id) {
    throw new Error('같은 Orshot 원본만 갱신할 수 있어요.')
  }
  const delta = (next.nativeLayout?.headerBottom ?? 0) - (original.nativeLayout?.headerBottom ?? 0)
  original.objects = [
    ...next.objects.filter((item) => item.hmId === 'canva-header'),
    ...original.objects.filter((item) => item.hmId !== 'canva-header'),
  ]
  if (original.nativeLayout && next.nativeLayout) {
    // 이전 가져오기의 공통 본문을 한 번만 원본 구성으로 전환한다.
    // 별도 objects에 저장한 HR의 본문 수정은 위에서 보존한다.
    if (!original.nativeLayout.sourceTemplate && next.nativeLayout.sourceTemplate) {
      original.nativeLayout = next.nativeLayout
    } else {
      original.nativeLayout.headerBottom = next.nativeLayout.headerBottom
      original.nativeLayout.sections = original.nativeLayout.sections.map((section) => ({
        ...section,
        top: section.top + delta,
      }))
    }
  }
  original.height += delta
  original.media = next.media
  original.orshotContentKey = next.orshotContentKey
  return JSON.stringify(original)
}

/** 원본의 큰 색 면에서 강조색을 골라 추가 본문도 같은 팔레트를 사용한다. */
export function orshotArtworkColor(pixels: Uint8ClampedArray, fallback: string): string {
  const buckets = new Map<string, { count: number; r: number; g: number; b: number }>()
  for (let at = 0; at < pixels.length; at += 64) {
    const [r, g, b] = pixels.slice(at, at + 3)
    const max = Math.max(r, g, b)
    const min = Math.min(r, g, b)
    if (max < 65 || max > 240 || max - min < 45 || pixels[at + 3] < 200) continue
    const key = [r, g, b].map((value) => Math.floor(value / 32)).join(',')
    const bucket = buckets.get(key) ?? { count: 0, r: 0, g: 0, b: 0 }
    bucket.count++
    bucket.r += r
    bucket.g += g
    bucket.b += b
    buckets.set(key, bucket)
  }
  const best = [...buckets.values()].sort((a, b) => b.count - a.count)[0]
  if (!best) return fallback
  return (
    '#' +
    [best.r, best.g, best.b]
      .map((value) =>
        Math.round(value / best.count)
          .toString(16)
          .padStart(2, '0'),
      )
      .join('')
  )
}

export async function importCanvaPoster(
  imported: Schemas['CanvaImport'],
  posting: PosterPosting,
  color: string,
): Promise<string> {
  const { template, mapping } = imported
  if (!/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(template.background))
    throw new Error('Canva 배경을 확인하지 못했어요.')
  const F = await import('fabric')
  await document.fonts.ready
  const image = await F.FabricImage.fromURL(template.background)
  const scale = 600 / template.width
  const pixels = image.toCanvasElement()
  const cleaned = clearCanvaLogoPlaceholder(pixels)
  const backgroundSource = cleaned ? pixels.toDataURL('image/jpeg', 0.8) : template.background
  const context = pixels.getContext('2d')
  const sample = (left: number, top: number, fallback: string) => {
    const pixel = context?.getImageData(
      Math.min(pixels.width - 1, Math.max(0, Math.floor((left / 600) * pixels.width))),
      Math.min(
        pixels.height - 1,
        Math.max(0, Math.floor((top / (template.height * scale)) * pixels.height)),
      ),
      1,
      1,
    ).data
    return pixel
      ? `#${[...pixel]
          .slice(0, 3)
          .map((v) => v.toString(16).padStart(2, '0'))
          .join('')}`
      : fallback
  }
  const body = mapping.bindings
    .filter(
      (m) => !['title', 'company', 'tags', 'tagline', 'notices', 'period'].includes(m.binding),
    )
    .map((m) => template.regions.find((r) => r.id === m.elementId))
    .filter((r) => r !== undefined)
  const bodyTop = Math.min(...body.map((r) => r.top * scale), template.height * scale * 0.55)
  const columns = !body.length || body.some((r) => r.left * scale > 300) ? 2 : 1
  const paper = sample(24, bodyTop + 8, '#f8f6f0')
  const header = sample(24, 60, '#082858')
  const rgb = [1, 3, 5].map((at) => Number.parseInt(header.slice(at, at + 2), 16))
  const onHeader = rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722 < 140 ? '#ffffff' : '#24313e'
  const bodyRgb = [1, 3, 5].map((at) => Number.parseInt(paper.slice(at, at + 2), 16))
  const ink =
    bodyRgb[0] * 0.2126 + bodyRgb[1] * 0.7152 + bodyRgb[2] * 0.0722 < 140 ? '#ffffff' : '#24313e'
  let accent = color
  // 원본 본문의 짧은 컬러 장식에서 강조색을 읽는다. 글자나 회사 사실은 복사하지 않는다.
  if (context) {
    const area = context.getImageData(0, 0, pixels.width, pixels.height).data
    let strongest = 45
    for (
      let y = Math.floor((bodyTop / (template.height * scale)) * pixels.height - 40);
      y < Math.min(pixels.height, Math.ceil((bodyTop / (template.height * scale)) * pixels.height));
      y += 2
    ) {
      if (y < 0) continue
      for (let x = Math.floor(pixels.width * 0.04); x < pixels.width * 0.2; x += 2) {
        const at = (y * pixels.width + x) * 4
        const channels = [area[at], area[at + 1], area[at + 2]]
        const saturation = Math.max(...channels) - Math.min(...channels)
        if (saturation > strongest) {
          strongest = saturation
          accent = `#${channels.map((v) => v.toString(16).padStart(2, '0')).join('')}`
        }
      }
    }
  }
  const values = posterBindings(posting)
  const objects: CanvasObject[] = []
  const text = (
    binding: string,
    left: number,
    top: number,
    width: number,
    fontSize: number,
    fill: string,
    row: number,
  ) => {
    if (!values[binding]) return 0
    const node = new F.Textbox(values[binding], {
      left,
      top,
      width,
      fontSize,
      fill,
      fontFamily: POSTER_FONT,
      originX: 'left',
      originY: 'top',
      splitByGrapheme: true,
      lineHeight: 1.6,
      fontWeight: ['company', 'title'].includes(binding) ? 'bold' : 'normal',
      styles:
        row >= 0
          ? {
              0: Object.fromEntries(
                [...values[binding].split('\n')[0]].map((_, index) => [
                  index,
                  { fontWeight: 'bold', fontSize: 18 },
                ]),
              ),
            }
          : {},
    })
    objects.push({ ...node.toObject(), text: '', hmId: binding, binding, hmFlowRow: row })
    return node.height
  }
  const companyRegion = mapping.bindings.find((m) => m.binding === 'company')
  const company = template.regions.find((r) => r.id === companyRegion?.elementId)
  const companyHeight = text(
    'company',
    company ? company.left * scale : 40,
    company ? company.top * scale : 36,
    company ? Math.max(200, Math.min(company.width * scale, 360)) : 360,
    17,
    onHeader,
    -1,
  )
  const titleHeight = text('title', 40, 96, 450, 40, onHeader, -1)
  const tagsTop = 96 + titleHeight + 22
  const tagsHeight = text('tags', 40, tagsTop, 520, 13, onHeader, -1)
  const headerHeight = Math.max(
    260,
    tagsTop + tagsHeight + 48,
    (company ? company.top * scale : 36) + companyHeight + 48,
  )
  image.set({
    left: 0,
    top: 0,
    originX: 'left',
    originY: 'top',
    width: image.width,
    height: Math.min(image.height, (headerHeight / scale / template.height) * image.height),
    scaleX: 600 / image.width,
    scaleY: (scale * template.height) / image.height,
  })
  const background: CanvasObject = {
    ...image.toObject(),
    src: backgroundSource,
    hmId: 'canva-header',
  }
  delete background.filters
  delete background.resizeFilter
  delete background.clipPath
  let top = headerHeight + 36
  const full = ['intro', 'conditions'].filter((key) => values[key])
  const blocks = ['duties', 'qualifications', 'preferred', 'benefits'].filter((key) => values[key])
  const rows: string[][] = full.map((key) => [key])
  for (let index = 0; index < blocks.length; index += columns)
    rows.push(blocks.slice(index, index + columns))
  for (const binding of ['stages', 'documents', 'notices', 'period']) {
    if (values[binding]) rows.push([binding])
  }
  rows.forEach((row, index) => {
    const heights = row.map((binding, column) =>
      text(binding, column ? 320 : 40, top + 20, row.length === 2 ? 240 : 520, 14, ink, index),
    )
    top += Math.max(...heights) + 64
  })
  const canvas: PosterCanvas = {
    width: 600,
    height: top + 12,
    brandColor: color,
    source: {
      id: `canva:${template.id}`,
      name: template.name.slice(0, 55),
      url: 'https://www.canva.com/',
      license: 'Canva 계정 디자인',
    },
    canvaLayout: {
      version: 2,
      headerHeight,
      paper,
      ink,
      accent,
      columns,
      logoFrameCleaned: true,
      logoCleanupVersion: 3,
    },
    objects: [background, ...objects],
  }
  const regions = mapping.bindings.flatMap((binding) => {
    if (['company', 'title', 'tags', 'tagline'].includes(binding.binding)) return []
    const region = template.regions.find((item) => item.id === binding.elementId)
    if (!region || region.width * scale < 90 || region.left * scale > 500) return []
    const left = Math.max(32, region.left * scale)
    return [
      {
        binding: binding.binding,
        left,
        top: region.top * scale,
        width: columns === 2 && left < 280 ? 300 - left - 24 : 600 - left - 40,
        height: Math.max(80, region.height * scale),
        heading: { fontSize: 18, fill: ink, fontWeight: 'bold' },
        body: { fontSize: 14, fill: ink, fontWeight: 'normal' },
        accent,
        rule: accent,
        card: paper,
        lastCard: accent,
        cardInk: ink,
      },
    ]
  })
  if (regions.length < 2)
    throw new Error(
      '원본 본문 구역을 충분히 읽지 못했어요. 다른 템플릿을 선택하거나 원본의 텍스트 영역을 확인해 주세요.',
    )
  const native: PosterCanvas = {
    ...canvas,
    nativeLayout: { version: 1, paper, headerBottom: headerHeight, sections: regions },
    objects: [
      background,
      ...objects.filter((object) =>
        ['company', 'title', 'tags', 'tagline'].includes(String(object.binding)),
      ),
    ],
  }
  const encoded = JSON.stringify(native)
  readPosterCanvas(encoded)
  return encoded
}

/** 이전에 저장한 이미지 덧씌우기 양식도 열 때 새 본문 구성으로 변환한다. */
export async function upgradeCanvaPoster(
  value: string,
  posting: PosterPosting,
  color: string,
): Promise<string> {
  const doc = readPosterCanvas(value)
  if (doc.nativeLayout) return value
  if (doc.source.url !== 'https://www.canva.com/') return value
  if (doc.canvaLayout) {
    const header = doc.objects.find((object) => object.hmId === 'canva-header')
    if (typeof header?.src !== 'string') return value
    if (doc.canvaLayout.logoCleanupVersion !== 3) {
      const F = await import('fabric')
      const image = await F.FabricImage.fromURL(header.src)
      const pixels = image.toCanvasElement()
      if (clearCanvaLogoPlaceholder(pixels)) header.src = pixels.toDataURL('image/jpeg', 0.8)
    }
    doc.canvaLayout.logoFrameCleaned = true
    doc.canvaLayout.logoCleanupVersion = 3
    const theme = doc.canvaLayout
    doc.nativeLayout = {
      version: 1,
      paper: theme.paper,
      headerBottom: theme.headerHeight,
      sections: doc.objects
        .filter(
          (object) =>
            typeof object.binding === 'string' &&
            !['company', 'title', 'tags', 'tagline'].includes(object.binding),
        )
        .map((object) => ({
          binding: object.binding as string,
          left: Number(object.left),
          top: Number(object.top),
          width: Number(object.width),
          height: Number(object.height ?? 100),
          heading: { fontSize: 18, fill: theme.ink, fontWeight: 'bold' },
          body: { fontSize: Number(object.fontSize ?? 14), fill: theme.ink, fontWeight: 'normal' },
          accent: theme.accent,
          rule: theme.accent,
          card: theme.paper,
          lastCard: theme.accent,
          cardInk: theme.ink,
        })),
    }
    doc.objects = doc.objects.filter(
      (object) =>
        !object.binding ||
        (typeof object.binding === 'string' &&
          ['company', 'title', 'tags', 'tagline'].includes(object.binding)),
    )
    return JSON.stringify(doc)
  }
  const background = doc.objects.find((object) => object.hmId === 'canva-background')
  if (!background || typeof background.src !== 'string') return value
  const height = Number(background.height) * Number(background.scaleY ?? 1)
  const regions = doc.objects
    .filter((object) => typeof object.binding === 'string')
    .map((object) => ({
      id: String(object.binding),
      text: '',
      left: Number(object.left),
      top: Number(object.top),
      width: Number(object.width),
      height: Number(object.height),
    }))
  return importCanvaPoster(
    {
      template: {
        id: doc.source.id?.replace(/^canva:/, '') ?? 'legacy',
        name: doc.source.name,
        editUrl: '',
        background: background.src,
        width: doc.width,
        height,
        regions,
      },
      mapping: {
        bindings: regions.map((region) => ({ elementId: region.id, binding: region.id })),
      },
    },
    posting,
    color,
  )
}

/** 본문 행은 실측 높이로 배치한다. 장식은 이미지를 늘리지 않고 행의 위치에 맞춰 그린다. */
export async function layoutCanvaPoster(
  target: StaticCanvas,
  doc: PosterCanvas,
  posting?: PosterPosting,
  design?: PosterDesign,
): Promise<void> {
  const theme = doc.canvaLayout
  if (!theme) return
  const F = await import('fabric')
  const nodes = target.getObjects()
  const byBinding = (binding: string) =>
    nodes.find((_, index) => doc.objects[index]?.binding === binding)
  const title = byBinding('title')
  const tags = byBinding('tags')
  if (title && tags) tags.set({ top: Math.max(186, title.top + title.getScaledHeight() + 22) })
  const company = byBinding('company')
  if (company instanceof F.Textbox && company.width < 200) {
    company.set({ width: Math.min(360, doc.width - company.left - 40) })
    company.initDimensions()
  }
  // 원본에서 회사명이 제목 아래에 있거나 오래된 저장 좌표가 남아 있어도 헤더 안에서 먼저 배치한다.
  // 세 헤더 문구가 차지하는 실제 높이를 모두 포함한 뒤 본문을 시작한다.
  const headerText = [company, title, tags, byBinding('tagline')]
    .filter((node) => node !== undefined)
    .sort((a, b) => a.top - b.top)
  for (let index = 0; index < headerText.length; index++) {
    const node = headerText[index]
    for (const previous of headerText.slice(0, index)) {
      if (
        node.left < previous.left + previous.getScaledWidth() &&
        previous.left < node.left + node.getScaledWidth()
      )
        node.set({ top: Math.max(node.top, previous.top + previous.getScaledHeight() + 20) })
    }
    node.setCoords()
  }
  const headerHeight = Math.max(
    theme.headerHeight,
    ...headerText.map((node) => node.top + node.getScaledHeight() + 48),
  )
  const header = nodes.find((_, index) => doc.objects[index]?.hmId === 'canva-header')
  if (header) header.set({ scaleY: headerHeight / header.height })
  const rows = new Map<number, typeof nodes>()
  nodes.forEach((node, index) => {
    const row = doc.objects[index]?.hmFlowRow
    if (typeof row !== 'number' || row < 0) return
    if (['stages', 'documents', 'notices', 'period'].includes(String(doc.objects[index]?.binding)))
      return
    rows.set(row, [...(rows.get(row) ?? []), node])
  })
  let last = Math.max(-1, ...rows.keys())
  for (const binding of ['stages', 'documents', 'notices', 'period']) {
    const node = byBinding(binding)
    if (!node) continue
    node.set({ left: 40, width: 520 })
    if (node instanceof F.Textbox) node.initDimensions()
    rows.set(++last, [node])
  }
  let top = headerHeight + 36
  for (const [, row] of [...rows].sort(([a], [b]) => a - b)) {
    target.add(
      new F.Rect({
        left: 40,
        top,
        width: 520,
        height: 1,
        fill: theme.ink,
        opacity: 0.2,
        originX: 'left',
        originY: 'top',
      }),
    )
    row.forEach((node) => {
      node.set({ top: top + 22 })
      node.setCoords()
      target.add(
        new F.Rect({
          left: node.left,
          top: top + 10,
          width: 26,
          height: 3,
          fill: theme.accent,
          originX: 'left',
          originY: 'top',
        }),
      )
    })
    let processHeight = 0
    const process = byBinding('stages')
    if (process instanceof F.Textbox && row.includes(process) && posting && design) {
      process.set({ text: '전형 절차' })
      process.initDimensions()
      processHeight =
        (await drawCanvasStages(
          target,
          posting,
          design,
          40,
          process.top + process.getScaledHeight() + 16,
          520,
          { card: theme.paper, final: theme.accent, fontSize: 13 },
        )) + 16
    }
    const rowHeight = Math.max(...row.map((node) => node.getScaledHeight())) + processHeight + 64
    if (row.length === 2)
      target.add(
        new F.Rect({
          left: 299,
          top: top + 12,
          width: 1,
          height: rowHeight - 24,
          fill: theme.ink,
          opacity: 0.18,
          originX: 'left',
          originY: 'top',
        }),
      )
    top += rowHeight
  }
  const height = top + 24
  if (height > 20000) throw new Error('포스터 내용이 너무 길어요.')
  target.setDimensions({ height })
  const paper = new F.Rect({
    left: 0,
    top: headerHeight,
    width: 600,
    height: height - headerHeight,
    fill: theme.paper,
    strokeWidth: 0,
    originX: 'left',
    originY: 'top',
  })
  target.add(paper)
  target.sendObjectToBack(paper)
  nodes.forEach((node) => node.setCoords())
}
