import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import type { Posting } from './api'
import type { PosterDesign } from './poster-design'
import {
  importOrshotPoster,
  orshotPostingKey,
  readPosterCanvas,
  refreshOrshotCanvas,
} from './poster-canvas'
import { api, unwrap } from '@/lib/api/client'

/** 이미지에 들어간 이전 공고 제목을 현재 저장된 공고로 갱신한다. */
export function useOrshotPoster(posting: Posting, design: PosterDesign) {
  const document = useMemo(() => {
    if (!design.canvasJson) return null
    try {
      const canvas = readPosterCanvas(design.canvasJson)
      return canvas.originalRender && canvas.source.id?.startsWith('orshot:') ? canvas : null
    } catch {
      return null
    }
  }, [design.canvasJson])
  const contentKey = orshotPostingKey(posting)
  const query = useQuery({
    queryKey: ['posting', posting.recruitmentId, 'orshot-header', document?.source.id, contentKey],
    enabled: posting.status === 'DRAFT' && !!document && document.orshotContentKey !== contentKey,
    staleTime: Infinity,
    retry: false,
    queryFn: async () => {
      const source = document!.source
      const imported = await unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/poster/orshot-import', {
          params: { path: { recruitmentId: posting.recruitmentId } },
          body: { templateId: Number(source.id!.slice('orshot:'.length)) },
        }),
      )
      return {
        sourceId: source.id,
        contentKey,
        canvasJson: await importOrshotPoster(
          { ...imported, name: source.name },
          design.color,
          true,
          posting,
        ),
      }
    },
  })
  const refreshed = query.data
  const updated = useMemo(() => {
    if (
      !document ||
      !design.canvasJson ||
      document.orshotContentKey === contentKey ||
      refreshed?.contentKey !== contentKey ||
      refreshed.sourceId !== document.source.id
    )
      return design
    return {
      ...design,
      canvasJson: refreshOrshotCanvas(design.canvasJson, refreshed.canvasJson),
      motion: 'NONE' as const,
    }
  }, [design, document, contentKey, refreshed])
  return { ...query, design: updated }
}
