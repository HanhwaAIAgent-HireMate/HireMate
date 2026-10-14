import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type Dashboard = Schemas['DashboardView']
export type RecruitmentCard = Schemas['RecruitmentCard']
export type StatusFilter = RecruitmentCard['status'] | 'ALL'

export function useDashboard(status: StatusFilter, query: string) {
  return useQuery({
    queryKey: ['recruitments', status, query],
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments', {
          params: {
            query: { status: status === 'ALL' ? undefined : status, query: query || undefined },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })
}

/** 채용 카드를 누르면 지금 진행 중인 단계로 간다. */
export function currentPath(card: RecruitmentCard) {
  const base = `/hr/recruitments/${card.recruitmentId}`
  switch (card.status) {
    case 'DRAFT':
      return `${base}/posting`
    case 'PUBLISHED':
      return `${base}/posting/status`
    case 'IN_PROGRESS':
      return card.currentStageId
        ? `${base}/stages/${card.currentStageId}`
        : `${base}/posting/status`
    case 'CLOSED':
      return `${base}/report`
  }
}
