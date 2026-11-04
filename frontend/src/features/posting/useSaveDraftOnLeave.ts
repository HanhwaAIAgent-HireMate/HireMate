import { useEffect, useRef } from 'react'
import { useBlocker } from 'react-router'
import { toast } from 'sonner'
import { errorMessage } from '@/lib/api/client'

/** 저장을 끝낸 뒤 이동한다. 실패하면 현재 편집 화면과 복구본을 유지한다. */
export function useSaveDraftOnLeave({
  enabled,
  isDirty,
  save,
}: {
  enabled: boolean
  isDirty: () => boolean
  save: () => Promise<boolean>
}) {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      enabled &&
      isDirty() &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  )
  const saving = useRef(false)
  useEffect(() => {
    if (blocker.state === 'unblocked') saving.current = false
    if (blocker.state !== 'blocked' || saving.current) return
    saving.current = true
    void save()
      .then((ok) => {
        if (ok) {
          toast.success('임시 저장했어요.')
          blocker.proceed()
        } else blocker.reset()
      })
      .catch((error: unknown) => {
        toast.error(errorMessage(error))
        blocker.reset()
      })
  }, [blocker, save])
}
