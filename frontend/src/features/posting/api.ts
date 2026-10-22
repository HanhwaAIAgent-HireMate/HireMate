import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type Posting = Schemas['PostingView']
export type PostingContent = Schemas['PostingContent']
export type PublicPosting = Schemas['PublicPostingView']
export type RequiredDocument = Schemas['RequiredDocument']

export const postingKeys = {
  posting: (recruitmentId: string) => ['posting', recruitmentId] as const,
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
    },
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
