import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'
import { stageKeys } from '@/features/screening/api'

export type Notice = Schemas['NoticeView']
export type NoticeGroup = Notice['group']
export type StageGuide = Schemas['StageGuide']
export type StageGuideView = Schemas['StageGuideView']
export type OnboardingGuide = Schemas['OnboardingGuide']

export const noticeKeys = { all: (stageId: string) => ['stage', stageId, 'notices'] as const }

export const stageGuideKeys = {
  all: (recruitmentId: string) => ['recruitment', recruitmentId, 'stage-guides'] as const,
  /** 전형 절차가 바뀌면(AI 수정안 적용) 전형 ID도 바뀌어 새로 받는다 */
  stages: (recruitmentId: string, stageIds: string) =>
    [...stageGuideKeys.all(recruitmentId), stageIds] as const,
}

/** 전형별 안내. 전형 결과 화면에서 다음 전형의 안내를 고친다. 첫 전형은 안내하는 메일이 없어 빠져 있다. */
export function useStageGuides(recruitmentId: string, stageIds: string) {
  return useQuery({
    queryKey: stageGuideKeys.stages(recruitmentId, stageIds),
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments/{recruitmentId}/stage-guides', {
          params: { path: { recruitmentId } },
        }),
      ),
  })
}

export function useSaveStageGuide(recruitmentId: string, stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: StageGuide) =>
      unwrap(api.PUT('/api/stages/{stageId}/guide', { params: { path: { stageId } }, body })),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: stageGuideKeys.all(recruitmentId) }),
        queryClient.invalidateQueries({ queryKey: ['interview-scheduling'] }),
        queryClient.invalidateQueries({
          predicate: ({ queryKey }) => queryKey[0] === 'stage' && queryKey[2] === 'notices',
        }),
      ])
    },
  })
}

/**
 * 결과를 확정한 전형의 안내 초안. 처음 열면 양식으로 초안을 만든다.
 * AI 초안은 기다리지 않는다. 안내 초안 화면에서 그룹마다 usePrepareNotice로 쓴다
 */
export function useNotices(stageId: string, enabled = true) {
  return useQuery({
    queryKey: noticeKeys.all(stageId),
    enabled,
    queryFn: () =>
      unwrap(api.GET('/api/stages/{stageId}/notices', { params: { path: { stageId } } })),
  })
}

/** AI 초안을 아직 쓰지 않은 안내. 보낼 사람이 있는데 본문이 비어 있다 */
export function needsDraft(notice: Notice) {
  return notice.status === 'DRAFT' && !notice.content.trim()
}

/**
 * Communication Agent가 그룹 하나의 초안을 쓴다(30초쯤). 다 쓰면 안내 목록을 바꾼다.
 * 실패하면 다시 시도할 때까지 부르지 않는다. 한 번에 수십 초 걸려서 자동으로 다시 부르지 않는다
 */
export function usePrepareNotice(stageId: string, group: NoticeGroup, enabled: boolean) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: [...noticeKeys.all(stageId), group, 'draft'],
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const notices = await unwrap(
        api.POST('/api/stages/{stageId}/notices/{group}/prepare', {
          params: { path: { stageId, group } },
        }),
      )
      queryClient.setQueryData(noticeKeys.all(stageId), notices)
      return notices
    },
  })
}

export function useEditNotice(stageId: string, group: NoticeGroup) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { subject: string; greeting: string; content: string; closing: string }) =>
      unwrap(
        api.PUT('/api/stages/{stageId}/notices/{group}', {
          params: { path: { stageId, group } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: noticeKeys.all(stageId) }),
  })
}

/** 최종 합격 안내의 입사 안내. 보내기 전까지 고칠 수 있다 */
export function useSaveOnboarding(stageId: string, group: NoticeGroup) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: OnboardingGuide) =>
      unwrap(
        api.PUT('/api/stages/{stageId}/notices/{group}/onboarding', {
          params: { path: { stageId, group } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: noticeKeys.all(stageId) }),
  })
}

export function useSendNotice(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (group: NoticeGroup) =>
      unwrap(
        api.POST('/api/stages/{stageId}/notices/{group}/send', {
          params: { path: { stageId, group } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: noticeKeys.all(stageId) }),
  })
}

/** 지원자가 받을 모습. 저장한 초안으로 backend가 보낼 때와 같은 HTML을 만든다. 초안을 고치면 새로 받는다 */
export function useNoticePreview(stageId: string, group: NoticeGroup, enabled: boolean) {
  return useQuery({
    queryKey: [...noticeKeys.all(stageId), group, 'preview'],
    enabled,
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/notices/{group}/preview', {
          params: { path: { stageId, group } },
        }),
      ),
  })
}

export function useNoticeAiRequest(stageId: string, group: NoticeGroup) {
  return useMutation({
    mutationFn: (message: string) =>
      unwrap(
        api.POST('/api/stages/{stageId}/notices/{group}/ai-requests', {
          params: { path: { stageId, group } },
          body: { message },
        }),
      ),
  })
}

/** 전형 종료. 다음 전형이 있으면 그 ID를 돌려준다. */
export function useFinishStage(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST('/api/stages/{stageId}/finish', { params: { path: { stageId } } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: stageKeys.all(stageId) })
      void queryClient.invalidateQueries({ queryKey: ['recruitments'] })
    },
  })
}

export const NOTICE_STATUS: Record<Notice['status'], { label: string; className: string }> = {
  DRAFT: { label: '초안 확인 중', className: 'bg-amber-100 text-amber-700' },
  SENT: { label: '발송 완료', className: 'bg-pass text-pass-foreground' },
  PARTIAL: { label: '일부 실패', className: 'bg-fail text-fail-foreground' },
  EMPTY: { label: '대상 없음', className: 'bg-muted text-muted-foreground' },
}

/** 안내 상태 표시. AI 초안을 아직 쓰지 않았으면 '초안 작성 전'이다 */
export function noticeBadge(notice: Notice) {
  return needsDraft(notice)
    ? { label: '초안 작성 전', className: 'bg-muted text-muted-foreground' }
    : NOTICE_STATUS[notice.status]
}
