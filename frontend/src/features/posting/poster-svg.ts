export const POSTER_FONT = 'Noto Sans KR Variable'

/** 측정과 출력이 같은 웹폰트를 쓰도록 독립 이미지 대신 문서 안의 SVG로 표시한다. */
export async function loadPosterFonts(text: string): Promise<void> {
  if (!document.fonts?.load) return
  await Promise.all(
    [400, 600, 700].map((weight) => document.fonts.load(`${weight} 16px "${POSTER_FONT}"`, text)),
  )
  await document.fonts.ready
}

/** Fabric이 만든 벡터만 허용하며 원본의 실행 요소·외부 참조는 문서에 넣지 않는다. */
export function inlinePosterSvg(value: string): string {
  const document = new DOMParser().parseFromString(value, 'image/svg+xml')
  const root = document.documentElement
  if (
    root.localName !== 'svg' ||
    root.querySelector('parsererror, script, style, foreignObject, iframe, object, a, use')
  )
    throw new Error('포스터 벡터 출력을 확인하지 못했어요.')
  for (const node of [root, ...root.querySelectorAll('*')]) {
    const id = node.getAttribute('id')
    if (id === 'poster-reveal-company' || id === 'poster-reveal-title') {
      node.setAttribute('data-poster-reveal', id.slice('poster-reveal-'.length))
      node.removeAttribute('id')
    }
    for (const attribute of [...node.attributes]) {
      if (/^on/i.test(attribute.name)) throw new Error('포스터에 지원하지 않는 속성이 있어요.')
      if (
        attribute.localName === 'href' &&
        !/^data:image\/(png|jpeg);base64,[\w+/=]+$/.test(attribute.value)
      )
        throw new Error('포스터에 외부 참조를 포함할 수 없어요.')
    }
  }
  root.setAttribute('width', '100%')
  root.setAttribute('height', 'auto')
  root.setAttribute('aria-hidden', 'true')
  return new XMLSerializer().serializeToString(root)
}
