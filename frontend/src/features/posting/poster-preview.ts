import type { PosterPosting } from './PostingPoster'
import type { PosterDesign } from './poster-design'
import { readPosterCanvas } from './poster-canvas'
import { resolvedStageIcon } from '@/features/recruit/stage-icons'

export type PosterChanges = { all: boolean; stages: string[]; bindings: string[] }

export function posterPreviewChanges(
  before: PosterDesign,
  after: PosterDesign,
  posting: PosterPosting,
): PosterChanges {
  const stages = posting.stages
    .filter(
      (stage) =>
        resolvedStageIcon(
          stage.type ?? 'INTERVIEW',
          before.stageIcons?.[stage.name],
          stage.name,
        ) !==
        resolvedStageIcon(stage.type ?? 'INTERVIEW', after.stageIcons?.[stage.name], stage.name),
    )
    .map((stage) => stage.name)
  const bindings = before.tagline !== after.tagline ? ['tagline'] : []
  let all = (
    ['template', 'color', 'mood', 'decoration', 'backgroundStyle', 'showLogo'] as const
  ).some((key) => before[key] !== after[key])
  if (JSON.stringify(before.readableSections) !== JSON.stringify(after.readableSections)) all = true
  if (before.canvasJson !== after.canvasJson) {
    try {
      const a = readPosterCanvas(before.canvasJson ?? ''),
        b = readPosterCanvas(after.canvasJson ?? '')
      if (a.source.id !== b.source.id) all = true
      else {
        for (const object of b.objects) {
          const old = a.objects.find((item) => item.hmId === object.hmId)
          if (JSON.stringify(old) !== JSON.stringify(object) && typeof object.hmId === 'string')
            bindings.push(object.hmId)
        }
        if (!bindings.length) all = true
      }
    } catch {
      all = true
    }
  }
  return { all, stages, bindings }
}
