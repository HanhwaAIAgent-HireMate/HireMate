import type { CSSProperties } from 'react'

import type { Schemas } from '@/lib/api/client'

export type PosterDesign = Schemas['PosterDesign']
export type PosterBrand = Schemas['PosterBrand']
export type PosterProposal = Schemas['PosterProposal']

export const POSTER_TEMPLATES = [
  {
    id: 'CLASSIC',
    name: '기본형',
    description: '명확한 구분선과 반듯한 정보 배치',
    color: '#24496c',
    mood: 'TRUST',
  },
  {
    id: 'EDITORIAL',
    name: '매거진형',
    description: '잡지처럼 나눈 본문과 따뜻한 여백',
    color: '#92583c',
    mood: 'WARM',
  },
  {
    id: 'BOLD',
    name: '강조형',
    description: '큰 번호와 대비가 선명한 모듈',
    color: '#6540ae',
    mood: 'LIVELY',
  },
  {
    id: 'PREMIUM',
    name: '심플형',
    description: '절제된 장식과 차분한 타이포그래피',
    color: '#79634b',
    mood: 'PREMIUM',
  },
  {
    id: 'NATURAL',
    name: '카드형',
    description: '둥근 본문 카드와 복지 타일',
    color: '#3e6b4e',
    mood: 'NATURAL',
  },
  {
    id: 'TICKET',
    name: '티켓형',
    description: '항목 라벨과 티켓 형태의 정보 구성',
    color: '#24606a',
    mood: 'TRUST',
  },
] as const satisfies readonly {
  id: PosterDesign['template']
  name: string
  description: string
  color: string
  mood: PosterDesign['mood']
}[]

export const POSTER_MOODS = [
  { id: 'TRUST', name: '깔끔하고 신뢰감 있게', color: '#2459a6' },
  { id: 'CLEAR', name: '맑고 청량하게', color: '#167ca7' },
  { id: 'WARM', name: '따뜻하고 친근하게', color: '#a26144' },
  { id: 'PREMIUM', name: '차분하고 고급스럽게', color: '#79634b' },
  { id: 'LIVELY', name: '경쾌하고 활기 있게', color: '#6840ad' },
  { id: 'NATURAL', name: '자연스럽고 부드럽게', color: '#3e6b4e' },
] as const satisfies readonly { id: PosterDesign['mood']; name: string; color: string }[]

export function initialPoster(brand?: PosterBrand): PosterDesign {
  return {
    template: POSTER_TEMPLATES.find((item) => item.id === brand?.template)?.id ?? 'CLASSIC',
    mood: POSTER_MOODS.find((item) => item.id === brand?.mood)?.id ?? 'TRUST',
    color: brand?.color ?? '#2459a6',
    decoration: brand?.decoration ?? 1,
    enabled: false,
    showLogo: Boolean(brand?.logoFileId),
    logoFileId: brand?.logoFileId ?? null,
    backgroundStyle: 'SOLID',
  }
}

function rgb(hex: string) {
  return [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16))
}

/** 대표 색의 연한 배경과 대비를 확보한 글자 색을 함께 만든다. */
export function posterPalette(color: string): CSSProperties {
  const safe = /^#[0-9a-f]{6}$/i.test(color) ? color : '#2459a6'
  const channels = rgb(safe)
  const luminance = channels
    .map((value) => {
      const channel = value / 255
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    })
    .reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0)
  const mix = (weight: number) =>
    `rgb(${channels.map((value) => Math.round(value * weight + 255 * (1 - weight))).join(' ')})`
  return {
    '--poster-primary': safe,
    '--poster-deep': `rgb(${channels.map((value) => Math.round(value * 0.4)).join(' ')})`,
    '--poster-on-primary': luminance > 0.179 ? '#17212b' : '#ffffff',
    '--poster-soft': mix(0.12),
    '--poster-line': mix(0.25),
    '--poster-heading': luminance > 0.35 ? '#263642' : safe,
  } as CSSProperties
}

/** 인쇄 대화상자의 PDF 저장을 사용해 글자와 웹 디자인을 보존한다. */
export async function exportPosterPdf(element: HTMLElement, title: string): Promise<void> {
  const frame = document.createElement('iframe')
  frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:800px;height:1100px;border:0'
  frame.title = '공고 PDF 출력'
  document.body.append(frame)
  const doc = frame.contentDocument
  const target = frame.contentWindow
  if (!doc || !target) {
    frame.remove()
    throw new Error('PDF 출력 창을 열지 못했어요.')
  }
  doc.title = title
  const base = doc.createElement('base')
  base.href = document.baseURI
  doc.head.append(base)
  const sheets: Promise<void>[] = []
  document.querySelectorAll('style, link[rel="stylesheet"]').forEach((node) => {
    const cloned = node.cloneNode(true)
    if (cloned instanceof HTMLLinkElement)
      sheets.push(
        new Promise((resolve, reject) => {
          cloned.onload = () => resolve()
          cloned.onerror = () => reject(new Error('PDF 스타일을 불러오지 못했어요.'))
        }),
      )
    doc.head.append(cloned)
  })
  const style = doc.createElement('style')
  style.textContent =
    '@page { size: A4; margin: 12mm; } html, body { margin: 0; padding: 0; background: white; color-scheme: light; } .posting-poster { width: 100%; max-width: none; box-shadow: none; border: 0; container-type: normal; } .poster-block, .poster-condition, .poster-step, .poster-brand { break-inside: avoid; } * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }'
  doc.head.append(style)
  doc.body.append(element.cloneNode(true))
  try {
    await Promise.all(sheets)
    await doc.fonts.ready
    await Promise.all(
      [...doc.images].map((image) =>
        image.complete
          ? Promise.resolve()
          : new Promise<void>((resolve) => {
              image.onload = () => resolve()
              image.onerror = () => resolve()
            }),
      ),
    )
    target.addEventListener('afterprint', () => frame.remove(), { once: true })
    target.focus()
    target.print()
    window.setTimeout(() => frame.remove(), 300_000)
  } catch (error) {
    frame.remove()
    throw error
  }
}
