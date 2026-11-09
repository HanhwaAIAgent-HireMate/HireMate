import type { StaticCanvas } from 'fabric'
import type { PosterPosting } from './PostingPoster'
import type { PosterDesign } from './poster-design'
import { posterBindings, posterCanvasObjects, readPosterCanvas } from './poster-canvas'
import { layoutNativePoster } from './poster-layout'
import { loadPosterFonts, POSTER_FONT } from './poster-svg'

type PosterCheck = {
  binding: string
  kind: 'CLIPPED' | 'OVERLAP' | 'MISSING'
  detail: string
}

/** 실제로 그린 글자와 현재 공고를 비교한다. 장식·이미지는 텍스트 겹침 대상으로 잡지 않는다. */
async function checkPoster(
  target: StaticCanvas,
  posting: PosterPosting,
  originalRender = false,
  fullRender = false,
) {
  // 전체 원본은 글자가 이미지 안에 있어 읽을 수 없다. 값은 백엔드가 자리마다 채우고 칸 맞춤은 원본이 맡는다.
  if (fullRender) return []
  const F = await import('fabric')
  const texts = target
    .getObjects()
    .filter(
      (node): node is InstanceType<typeof F.FabricText> =>
        node instanceof F.FabricText &&
        node.visible &&
        node.opacity > 0.05 &&
        !node.excludeFromExport &&
        (typeof node.fill !== 'string' || new F.Color(node.fill).getAlpha() > 0.05),
    )
  const checks: PosterCheck[] = []
  const binding = (node: (typeof texts)[number]) =>
    String(node.get('hmId') ?? 'all').replace(/[:].*$/, '')
  for (const node of texts) {
    const b = node.getBoundingRect()
    if (
      b.left < -2 ||
      b.top < -2 ||
      b.left + b.width > target.width + 2 ||
      b.top + b.height > target.height + 2
    )
      checks.push({
        binding: binding(node),
        kind: 'CLIPPED',
        detail: '텍스트가 포스터 영역을 벗어납니다.',
      })
  }
  for (let i = 0; i < texts.length; i++) {
    for (let j = i + 1; j < texts.length; j++) {
      const a = texts[i].getBoundingRect(),
        b = texts[j].getBoundingRect()
      const width = Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left)
      const height = Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top)
      if (
        width > 4 &&
        height > 3 &&
        width * height > Math.min(a.width * a.height, b.width * b.height) * 0.08
      )
        checks.push({
          binding: binding(texts[j]),
          kind: 'OVERLAP',
          detail: `${binding(texts[i])} 영역과 글자가 겹칩니다.`,
        })
    }
  }
  const normalize = (value: string) => value.normalize('NFKC').replace(/\s+/g, '')
  const visible = normalize(texts.map((node) => node.text).join('\n'))
  const expected = {
    ...(originalRender
      ? {}
      : {
          company: [posting.companyName],
          title: [posting.content.title],
          tags: [posting.content.location, posting.content.employmentType, posting.content.career],
        }),
    intro: [posting.content.intro],
    duties: posting.content.duties,
    qualifications: posting.content.qualifications,
    preferred: posting.content.preferred,
    benefits: posting.content.benefits,
    notices: posting.notices,
    stages: posting.stages.map((stage) => stage.name),
    documents: posting.documents.map((item) => item.label),
    conditions: [
      posting.content.salary,
      posting.content.education,
      posting.content.position,
      posting.content.workHours,
    ],
  }
  for (const [key, values] of Object.entries(expected)) {
    if (values.some((value) => value.trim() && !visible.includes(normalize(value))))
      checks.push({
        binding: key,
        kind: 'MISSING',
        detail: '현재 공고 내용 일부가 출력에 없습니다.',
      })
  }
  return checks
}

/** 실제 공고 내용으로 원본을 배치하고, 표시 전에 잘림·겹침·누락을 확인한다. */
export async function assertTemplatedPreview(posting: PosterPosting, design: PosterDesign) {
  const doc = readPosterCanvas(design.canvasJson!)
  if (!doc.source.id?.startsWith('templated:') || !doc.nativeLayout) return
  const values = posterBindings(posting, design)
  await loadPosterFonts(Object.values(values).join('\n'))
  const F = await import('fabric')
  F.cache.clearFontCache(POSTER_FONT)
  const target = new F.StaticCanvas(document.createElement('canvas'), {
    width: doc.width,
    height: doc.height,
  })
  try {
    await target.loadFromJSON({ objects: posterCanvasObjects(doc, values, design.color) })
    await layoutNativePoster(target, doc, posting, design)
    if ((await checkPoster(target, posting)).length)
      throw new Error('공고의 잘림·겹침·내용 누락 검사를 통과하지 못했어요.')
  } finally {
    await target.dispose()
  }
}
