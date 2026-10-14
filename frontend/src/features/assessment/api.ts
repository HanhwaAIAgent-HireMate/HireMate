import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError, unwrap, type Schemas } from '@/lib/api/client'
import { stageKeys } from '@/features/screening/api'

export type AssessmentResult = Schemas['AssessmentResultView']
export type TablePreview = Schemas['TablePreview']
export type ImportRow = Schemas['ImportRow']
export type IdentifierType = Schemas['ImportRequest']['identifierType']

/** NCS 기준 5개 영역 (OI-03 MVP 기본값) */
export const NCS_AREAS = [
  '의사소통능력',
  '수리능력',
  '문제해결능력',
  '정보능력',
  '기술능력',
] as const

const resultKey = (stageId: string, applicationId: string) => [
  ...stageKeys.all(stageId),
  'assessment',
  applicationId,
]

export function useAssessmentResult(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: resultKey(stageId, applicationId),
    queryFn: async () => {
      try {
        return await unwrap(
          api.GET('/api/stages/{stageId}/assessment/results/{applicationId}', {
            params: { path: { stageId, applicationId } },
          }),
        )
      } catch (error) {
        if (error instanceof ApiError && error.code === 'RESULT_NOT_FOUND') return null
        throw error
      }
    },
  })
}

export function usePreviewTable(stageId: string) {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return unwrap(
        api.POST('/api/stages/{stageId}/assessment/preview', {
          params: { path: { stageId } },
          body: form as unknown as { file: string },
        }),
      )
    },
  })
}

export function useImportResults(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      dryRun,
      identifierType,
      entries,
    }: {
      dryRun: boolean
      identifierType: IdentifierType
      entries: ImportRow[]
    }) =>
      unwrap(
        api.POST('/api/stages/{stageId}/assessment/import', {
          params: { path: { stageId }, query: { dryRun } },
          body: { identifierType, entries },
        }),
      ),
    onSuccess: (result) => {
      if (result.saved) void queryClient.invalidateQueries({ queryKey: stageKeys.all(stageId) })
    },
  })
}

export function useSaveResult(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      applicationId,
      ...body
    }: { applicationId: string } & Schemas['ManualResultRequest']) =>
      unwrap(
        api.PUT('/api/stages/{stageId}/assessment/results/{applicationId}', {
          params: { path: { stageId, applicationId } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: stageKeys.all(stageId) }),
  })
}

export function useAttachResultFile(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ applicationId, file }: { applicationId: string; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      return unwrap(
        api.POST('/api/stages/{stageId}/assessment/results/{applicationId}/file', {
          params: { path: { stageId, applicationId } },
          body: form as unknown as { file: string },
        }),
      )
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: stageKeys.all(stageId) }),
  })
}

export function resultFileUrl(stageId: string, applicationId: string) {
  return `/api/stages/${stageId}/assessment/results/${applicationId}/file`
}
