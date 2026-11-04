import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { SettingsSection } from '@/features/company/SettingsSection'
import { api, errorMessage, unwrap } from '@/lib/api/client'

const connectionKey = ['company', 'canva-connection'] as const

export function CanvaConnection() {
  const query = useQueryClient()
  const [params, setParams] = useSearchParams()
  const connection = useQuery({
    queryKey: connectionKey,
    queryFn: () => unwrap(api.GET('/api/companies/me/canva')),
  })
  const connect = useMutation({
    mutationFn: () => unwrap(api.POST('/api/companies/me/canva/authorization')),
    onSuccess: ({ url }) => globalThis.location.assign(url),
    onError: (error) => toast.error(errorMessage(error)),
  })
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST('/api/companies/me/canva/verify')),
    onSuccess: (data) => {
      query.setQueryData(connectionKey, data)
      toast.success('Canva 연결과 사용할 수 있는 기능을 확인했어요.')
    },
    onError: (error) => {
      void query.invalidateQueries({ queryKey: connectionKey })
      toast.error(errorMessage(error))
    },
  })
  const disconnect = useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/companies/me/canva')),
    onSuccess: () => {
      void query.invalidateQueries({ queryKey: connectionKey })
      toast.success('HireMate의 Canva 연결을 해제했어요.')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
  useEffect(() => {
    const result = params.get('canva')
    if (!result) return
    if (result === 'connected') toast.success('Canva 계정이 연결됐어요.')
    else if (result === 'denied') toast.info('Canva 연결 승인이 취소됐어요.')
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('canva')
        return next
      },
      { replace: true },
    )
    void query.invalidateQueries({ queryKey: connectionKey })
  }, [params, setParams, query])
  const busy = connect.isPending || verify.isPending || disconnect.isPending
  const beginConnection = () => {
    if (!connection.data) return
    const origin = new URL(connection.data.redirectUri).origin
    if (origin !== globalThis.location.origin) {
      // OAuth callback과 시작 화면의 호스트가 같아야 로그인 세션 쿠키가 유지된다.
      globalThis.location.assign(`${origin}/hr/settings/posting`)
      return
    }
    connect.mutate()
  }
  return (
    <SettingsSection title="Canva 연결">
      <p className="text-sm text-muted-foreground">
        내 Canva 계정을 연결하고 현재 사용할 수 있는 기능을 확인해요. 연결은 현재 HireMate 로그인
        세션 동안 유지돼요.
      </p>
      {connection.isError && <p role="alert">Canva 연결 상태를 불러오지 못했어요.</p>}
      {connection.data && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm">{connection.data.connected ? '연결됨' : '연결되지 않음'}</span>
          {connection.data.connected ? (
            <>
              <Button variant="outline" disabled={busy} onClick={() => verify.mutate()}>
                연결 확인
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => disconnect.mutate()}>
                연결 해제
              </Button>
            </>
          ) : (
            <Button disabled={busy || !connection.data.configured} onClick={beginConnection}>
              {connect.isPending ? '연결 중…' : 'Canva 계정 연결'}
            </Button>
          )}
        </div>
      )}
      {connection.data && !connection.data.configured && (
        <p className="text-sm text-muted-foreground">
          Canva를 연결하려면 먼저 서버 연결 설정이 필요해요.
        </p>
      )}
      {connection.data?.connected && (
        <p className="text-xs text-muted-foreground">
          포스터 채팅에서 내 Canva 디자인을 찾을 수 있어요. 가져온 배경 장식은 원본 형태로 유지되고,
          공고 글자와 배치는 편집할 수 있어요.
        </p>
      )}
    </SettingsSection>
  )
}
