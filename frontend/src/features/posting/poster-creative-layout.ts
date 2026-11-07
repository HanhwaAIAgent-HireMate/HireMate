import type { NativeLayout } from './poster-layout'
import { ORSHOT_SOURCE_LAYOUTS } from './orshot-source-layouts'

const palettes: Record<string, { primary: string; accent: string }> = {
  MAGAZINE: { primary: '#172820', accent: '#C9F565' },
  COLLAGE: { primary: '#252A64', accent: '#F26245' },
  FEATURE: { primary: '#4C2584', accent: '#B5D970' },
  POSTCARD: { primary: '#17191C', accent: '#FFCF42' },
  CINEMA: { primary: '#132D3B', accent: '#F4AC75' },
  TYPE: { primary: '#152F28', accent: '#D8F779' },
  AURORA: { primary: '#18254D', accent: '#AC9DE8' },
  RIBBON: { primary: '#602F56', accent: '#FE9A80' },
  ORBIT: { primary: '#163E48', accent: '#F2C462' },
}

export function creativeOrshotColor(style: string | null | undefined) {
  return style ? palettes[style]?.primary : undefined
}

/** 원본의 항목 순서와 실제 스타일을 유지한다. 본문은 source renderer가 길이만 늘린다. */
export function creativeOrshotLayout(
  style: string | null | undefined,
  base: NativeLayout,
): NativeLayout {
  const source = style ? ORSHOT_SOURCE_LAYOUTS[style] : undefined
  if (!source || !style) return base
  const sections = base.sections.map((original) => {
    const section = source.sections.find((item) => item.binding === original.binding)
    if (!section) return original
    const left = Math.min(section.heading.left, section.body.left)
    return {
      ...original,
      left,
      width:
        Math.max(
          section.heading.left + section.heading.width,
          section.body.left + section.body.width,
        ) - left,
      top: Math.min(section.heading.top, section.body.top),
      heading: {
        fontSize: section.heading.size,
        fill: section.heading.color,
        fontWeight: section.heading.weight,
      },
      body: {
        fontSize: section.body.size,
        fill: section.body.color,
        fontWeight: section.body.weight,
      },
    }
  })
  return { ...base, sourceTemplate: style, paper: source.paper, sections }
}
