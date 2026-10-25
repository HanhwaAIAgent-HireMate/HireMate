import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type Posting = Schemas['PostingView']
export type PostingContent = Schemas['PostingContent']
export type PublicPosting = Schemas['PublicPostingView']
export type RequiredDocument = Schemas['RequiredDocument']
export type ScreeningCriteria = Schemas['ScreeningCriteriaView']
export type CriterionItem = Schemas['CriterionItem']
export type CriteriaRequest = Schemas['CriteriaRequest']
export type CriterionInput = Schemas['CriterionInput']

export const postingKeys = {
  posting: (recruitmentId: string) => ['posting', recruitmentId] as const,
  criteria: (recruitmentId: string) => ['posting-criteria', recruitmentId] as const,
  public: (postingId: string) => ['public-posting', postingId] as const,
}

export function usePosting(recruitmentId: string) {
  return useQuery({
    queryKey: postingKeys.posting(recruitmentId),
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments/{recruitmentId}/posting', {
          params: { path: { recruitmentId } },
        }),
      ),
  })
}

export function useCreateRecruitment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/recruitments')),
    onSuccess: (posting) =>
      queryClient.setQueryData(postingKeys.posting(posting.recruitmentId), posting),
  })
}

/** 서버가 돌려준 공고로 캐시를 바꾸는 변경 요청들 */
function usePostingMutation<T>(recruitmentId: string, request: (variables: T) => Promise<Posting>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: (posting) => {
      queryClient.setQueryData(postingKeys.posting(recruitmentId), posting)
      void queryClient.invalidateQueries({ queryKey: ['recruitments'] })
      // 평가 기준은 자격 요건 · 우대 사항 문장과 짝을 맞춰서, 문장이 바뀌면 다시 불러온다
      void queryClient.invalidateQueries({ queryKey: postingKeys.criteria(recruitmentId) })
    },
  })
}

/** 서류 평가 기준과 선발 인원. 자격 요건 · 우대 사항마다 저장한 기준을 짝지어 받는다 */
export function useScreeningCriteria(recruitmentId: string) {
  return useQuery({
    queryKey: postingKeys.criteria(recruitmentId),
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments/{recruitmentId}/posting/criteria', {
          params: { path: { recruitmentId } },
        }),
      ),
  })
}

export type CriterionDraft = Schemas['CriterionDraft']
export type ImportantAdvice = Schemas['ImportantAdvice']

/** 평가 기준 항목 하나의 AI 초안. 저장하지 않고 입력 칸만 채운다 */
export function useDraftCriterion(recruitmentId: string) {
  return useMutation({
    mutationFn: (body: Schemas['CriterionDraftRequest']) =>
      unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/criteria/draft', {
          params: { path: { recruitmentId } },
          body,
        }),
      ),
  })
}

/** 목록마다 '중요'로 추천할 항목 */
export function useRecommendImportant(recruitmentId: string) {
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/criteria/important', {
          params: { path: { recruitmentId } },
        }),
      ),
  })
}

/** 서류 평가 기준 저장. 게시 전에만 고칠 수 있다 */
export function useSaveScreeningCriteria(recruitmentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CriteriaRequest) =>
      unwrap(
        api.PUT('/api/recruitments/{recruitmentId}/posting/criteria', {
          params: { path: { recruitmentId } },
          body,
        }),
      ),
    onSuccess: (criteria) =>
      queryClient.setQueryData(postingKeys.criteria(recruitmentId), criteria),
  })
}

export function useSavePosting(recruitmentId: string) {
  return usePostingMutation(recruitmentId, (body: PostingContent) =>
    unwrap(
      api.PUT('/api/recruitments/{recruitmentId}/posting', {
        params: { path: { recruitmentId } },
        body,
      }),
    ),
  )
}

/** 접수 확인 메일. 게시 전에만 고칠 수 있다 */
export function useSaveReceipt(recruitmentId: string) {
  return usePostingMutation(recruitmentId, (body: { subject: string; body: string }) =>
    unwrap(
      api.PUT('/api/recruitments/{recruitmentId}/posting/receipt', {
        params: { path: { recruitmentId } },
        body,
      }),
    ),
  )
}

export function useApplySuggestion(recruitmentId: string) {
  return usePostingMutation(recruitmentId, () =>
    unwrap(
      api.POST('/api/recruitments/{recruitmentId}/posting/suggestion/apply', {
        params: { path: { recruitmentId } },
      }),
    ),
  )
}

export function useDiscardSuggestion(recruitmentId: string) {
  return usePostingMutation(recruitmentId, () =>
    unwrap(
      api.POST('/api/recruitments/{recruitmentId}/posting/suggestion/discard', {
        params: { path: { recruitmentId } },
      }),
    ),
  )
}

export function usePublishPosting(recruitmentId: string) {
  return usePostingMutation(recruitmentId, (body: { openAt: string; closeAt: string }) =>
    unwrap(
      api.POST('/api/recruitments/{recruitmentId}/posting/publish', {
        params: { path: { recruitmentId } },
        body,
      }),
    ),
  )
}

export function useClosePosting(recruitmentId: string) {
  return usePostingMutation(recruitmentId, () =>
    unwrap(
      api.POST('/api/recruitments/{recruitmentId}/posting/close', {
        params: { path: { recruitmentId } },
      }),
    ),
  )
}

/** [AI 수정 요청]. 수정안이 생기면 공고 캐시의 suggestion이 바뀐다. */
export function usePostingAiRequest(recruitmentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (message: string) =>
      unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/ai-requests', {
          params: { path: { recruitmentId } },
          body: { message },
        }),
      ),
    onSuccess: (answer) =>
      queryClient.setQueryData(postingKeys.posting(recruitmentId), answer.posting),
  })
}

export function usePublicPosting(postingId: string) {
  return useQuery({
    queryKey: postingKeys.public(postingId),
    queryFn: () =>
      unwrap(api.GET('/api/public/postings/{postingId}', { params: { path: { postingId } } })),
  })
}
