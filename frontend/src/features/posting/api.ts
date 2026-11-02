import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type Posting = Schemas['PostingView']
export type PostingContent = Schemas['PostingContent']
export type PostingFocus = Schemas['PostingFocus']
export type PublicPosting = Schemas['PublicPostingView']
export type RequiredDocument = Schemas['RequiredDocument']
/** 서류 필수 조건. HR이 공고 작성 화면에서 '필수'로 표시한 줄이다. 지원자에게는 보내지 않는다 */
export type RequiredCriteria = Schemas['RequiredCriteria']

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

/** 본문과 서류 필수 조건을 함께 저장한다. required가 null이면 저장된 표시를 그대로 둔다 */
export function useSavePosting(recruitmentId: string) {
  return usePostingMutation(
    recruitmentId,
    ({ content, required }: { content: PostingContent; required: RequiredCriteria | null }) =>
      unwrap(
        api.PUT('/api/recruitments/{recruitmentId}/posting', {
          params: { path: { recruitmentId } },
          body: {
            ...content,
            requiredQualifications: required?.qualifications ?? null,
            requiredPreferred: required?.preferred ?? null,
          },
        }),
      ),
  )
}

/** 지원자가 받을 접수 확인 메일. 저장한 템플릿으로 backend가 보낼 때와 같은 HTML을 만든다 */
export function useReceiptPreview(recruitmentId: string) {
  return useQuery({
    queryKey: [...postingKeys.posting(recruitmentId), 'receipt-preview'],
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments/{recruitmentId}/posting/receipt/preview', {
          params: { path: { recruitmentId } },
        }),
      ),
  })
}

/** HR이 직접 정한 전형 절차. 게시 전에만 바꿀 수 있고, 이름이 같은 전형은 입력해 둔 안내를 이어 받는다 */
export function useSaveStages(recruitmentId: string) {
  return usePostingMutation(recruitmentId, (stages: Schemas['StageItem'][]) =>
    unwrap(
      api.PUT('/api/recruitments/{recruitmentId}/posting/stages', {
        params: { path: { recruitmentId } },
        body: { stages },
      }),
    ),
  )
}

/** 수정안 적용. fields가 있으면 그 칸만 적용하고 나머지는 수정안으로 남긴다 */
export function useApplySuggestion(recruitmentId: string) {
  return usePostingMutation(recruitmentId, (fields?: string[]) =>
    unwrap(
      api.POST('/api/recruitments/{recruitmentId}/posting/suggestion/apply', {
        params: { path: { recruitmentId } },
        body: fields ? { fields } : undefined,
      }),
    ),
  )
}

/** 수정안 되돌리기. fields가 있으면 그 칸만 되돌리고 나머지는 수정안으로 남긴다 */
export function useDiscardSuggestion(recruitmentId: string) {
  return usePostingMutation(recruitmentId, (fields?: string[]) =>
    unwrap(
      api.POST('/api/recruitments/{recruitmentId}/posting/suggestion/discard', {
        params: { path: { recruitmentId } },
        body: fields ? { fields } : undefined,
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

/** [AI 수정 요청]. focus가 있으면 그 줄만 고친다. 수정안이 생기면 공고 캐시의 suggestion이 바뀐다. */
export function usePostingAiRequest(recruitmentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ message, focus }: { message: string; focus: PostingFocus | null }) =>
      unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/ai-requests', {
          params: { path: { recruitmentId } },
          body: { message, focus },
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
