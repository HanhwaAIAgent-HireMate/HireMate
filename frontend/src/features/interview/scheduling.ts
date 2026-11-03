import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'

export const schedulingKey = (stageId: string) => ['interview-scheduling', stageId] as const

export function useInterviewScheduling(stageId: string, enabled = true) {
  return useQuery({
    queryKey: schedulingKey(stageId),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/interview-scheduling', { params: { path: { stageId } } }),
      ),
    refetchInterval: (query) => (query.state.data?.status === 'PENDING' ? 1000 : false),
  })
}

export function useRetryInterviewScheduling(stageId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/stages/{stageId}/interview-scheduling/retry', {
          params: { path: { stageId } },
        }),
      ),
    onSuccess: (state) => client.setQueryData(schedulingKey(stageId), state),
  })
}
