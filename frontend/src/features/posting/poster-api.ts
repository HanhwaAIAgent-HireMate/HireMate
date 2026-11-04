import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { postingKeys } from '@/features/posting/api'
import type { PosterBrand, PosterDesign } from '@/features/posting/poster-design'
import { api, unwrap, type Schemas } from '@/lib/api/client'

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
    mutationFn: (body: {
      message: string
      design: PosterDesign
      history?: Schemas['PosterTurn'][]
      sectionNames?: string[]
    }) =>
      unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/poster/ai-requests', {
          params: { path: { recruitmentId } },
          body: { ...body, history: body.history ?? [], sectionNames: body.sectionNames ?? [] },
        }),
      ),
  })
}

export function savedPosterLogoUrl(recruitmentId: string, logoId?: string | null) {
  return `/api/recruitments/${recruitmentId}/posting/poster/logo?v=${logoId ?? ''}`
}

export function companyPosterLogoUrl(logoId?: string | null) {
  return `/api/companies/me/poster-brand/logo?v=${logoId ?? ''}`
}
