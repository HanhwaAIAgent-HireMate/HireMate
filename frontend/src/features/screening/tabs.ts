import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { stageKeys } from '@/features/screening/api'
import { api, unwrap, type Schemas } from '@/lib/api/client'

/** 전형 화면의 탭: 선택 지원자와 AI Chat 대화의 묶음. 같은 기업 담당자가 함께 쓴다. */
export type StageTab = Schemas['StageTabView']

/** 전형마다 만들 수 있는 탭 수 */
export const MAX_TABS = 20

/** 열 탭. 주소의 탭이 없거나 지워졌으면 첫 탭이고, 탭이 없으면(시작하지 않은 전형) null이다 */
export function pickTab(tabs: Pick<StageTab, 'id'>[], wanted: string | null): string | null {
  if (tabs.length === 0) return null
  return tabs.some((tab) => tab.id === wanted) ? wanted : tabs[0].id
}

/** 지운 탭 대신 열 탭. 다음 탭, 마지막 탭이면 앞 탭이다 */
export function neighborTab(tabs: Pick<StageTab, 'id'>[], removed: string): string | null {
  const index = tabs.findIndex((tab) => tab.id === removed)
  const rest = tabs.filter((tab) => tab.id !== removed)
  if (rest.length === 0) return null
  return rest[Math.min(Math.max(index, 0), rest.length - 1)].id
}

export function useStageTabs(stageId: string) {
  return useQuery({
    queryKey: stageKeys.tabs(stageId),
    queryFn: () => unwrap(api.GET('/api/stages/{stageId}/tabs', { params: { path: { stageId } } })),
  })
}

/** 지금 탭. 주소의 ?tab=으로 고르고, 새로 고침하거나 주소를 보내도 같은 탭이 열린다 */
export function useCurrentTab(stageId: string) {
  const tabs = useStageTabs(stageId)
  const [params, setParams] = useSearchParams()
  const list = tabs.data ?? []
  const tabId = pickTab(list, params.get('tab'))
  const setTab = (id: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.set('tab', id)
        return next
      },
      { replace: true },
    )
  return { tabs, tab: list.find((item) => item.id === tabId) ?? null, tabId, setTab }
}

export function useTabActions(stageId: string) {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: stageKeys.tabs(stageId) })
  const tabPath = (tabId: string) => ({ params: { path: { stageId, tabId } } })
  return {
    create: useMutation({
      mutationFn: () =>
        unwrap(api.POST('/api/stages/{stageId}/tabs', { params: { path: { stageId } } })),
      onSettled: refresh,
    }),
    rename: useMutation({
      mutationFn: ({ tabId, name }: { tabId: string; name: string }) =>
        unwrap(
          api.PATCH('/api/stages/{stageId}/tabs/{tabId}', { ...tabPath(tabId), body: { name } }),
        ),
      onSettled: refresh,
    }),
    remove: useMutation({
      mutationFn: (tabId: string) =>
        unwrap(api.DELETE('/api/stages/{stageId}/tabs/{tabId}', tabPath(tabId))),
      onSettled: refresh,
    }),
  }
}
