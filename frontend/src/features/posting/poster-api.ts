import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { postingKeys } from '@/features/posting/api'
import type { PosterBrand, PosterDesign } from '@/features/posting/poster-design'
import { api, ApiError, unwrap, type Schemas } from '@/lib/api/client'
import { readEvents } from '@/lib/api/sse'
import type { ChatStep } from '@/features/chat/steps'

export const posterBrandKey = ['company', 'poster-brand'] as const

export function usePosterBrand() {
  return useQuery({
    queryKey: posterBrandKey,
    queryFn: () => unwrap(api.GET('/api/companies/me/poster-brand')),
  })
}

export function useSavePosterBrand() {
  const query = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['PosterBrandRequest']) =>
      unwrap(api.PUT('/api/companies/me/poster-brand', { body })),
    onSuccess: (brand: PosterBrand) => query.setQueryData(posterBrandKey, brand),
  })
}

export function useAddPosterTemplate() {
  const query = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['PosterTemplateRequest']) =>
      unwrap(api.POST('/api/companies/me/poster-brand/templates', { body })),
    onSuccess: async (brand: PosterBrand) => {
      await query.cancelQueries({ queryKey: posterBrandKey })
      query.setQueryData(posterBrandKey, brand)
      await query.invalidateQueries({ queryKey: posterBrandKey })
    },
  })
}

export function useSavePoster(recruitmentId: string) {
  const query = useQueryClient()
  return useMutation({
    mutationFn: (body: PosterDesign) =>
      unwrap(
        api.PUT('/api/recruitments/{recruitmentId}/posting/poster', {
          params: { path: { recruitmentId } },
          body,
        }),
      ),
    onSuccess: (posting) => query.setQueryData(postingKeys.posting(recruitmentId), posting),
  })
}

export function useDeletePosterTemplate() {
  const query = useQueryClient()
  return useMutation({
    mutationFn: (templateId: string) =>
      unwrap(
        api.DELETE('/api/companies/me/poster-brand/templates/{templateId}', {
          params: { path: { templateId } },
        }),
      ),
    onSuccess: (brand: PosterBrand) => query.setQueryData(posterBrandKey, brand),
  })
}

export function usePosterAi(recruitmentId: string) {
  return useMutation({
    mutationFn: async ({
      onStep,
      ...body
    }: {
      message: string
      design: PosterDesign
      history?: Schemas['PosterTurn'][]
      sectionNames?: string[]
      onStep?: (step: ChatStep) => void
    }) => {
      const stream = await unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/poster/ai-requests/stream', {
          params: { path: { recruitmentId } },
          body: { ...body, history: body.history ?? [], sectionNames: body.sectionNames ?? [] },
          parseAs: 'stream',
        }),
      )
      if (!stream) throw new ApiError(502, 'AI_UNAVAILABLE', '')
      return readPosterProposal(stream, onStep ?? (() => {}))
    },
  })
}

export async function readPosterProposal(
  stream: ReadableStream<Uint8Array>,
  onStep: (step: ChatStep) => void,
): Promise<Schemas['PosterProposal']> {
  for await (const { event, data } of readEvents(stream)) {
    if (event === 'status') onStep(JSON.parse(data) as ChatStep)
    else if (event === 'done') return JSON.parse(data) as Schemas['PosterProposal']
    else if (event === 'error') {
      const error = JSON.parse(data) as Schemas['ChatError']
      throw new ApiError(error.status, error.code, '')
    }
  }
  throw new ApiError(502, 'AI_UNAVAILABLE', '')
}

export function savedPosterLogoUrl(recruitmentId: string, logoId?: string | null) {
  return `/api/recruitments/${recruitmentId}/posting/poster/logo?v=${logoId ?? ''}`
}

export function companyPosterLogoUrl(logoId?: string | null) {
  return `/api/companies/me/poster-brand/logo?v=${logoId ?? ''}`
}
