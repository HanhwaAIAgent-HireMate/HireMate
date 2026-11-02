import { useQuery } from '@tanstack/react-query'
import { Bell } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { api, unwrap } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

/** 시작한 면접은 실시간 연결 없이 이 간격으로 다시 받아 온다 */
const STARTED_POLL_MS = 15_000

/** 최근 시작한 면접 (최근 7일, 최근 것부터 20개) */
function useStartedInterviews() {
  return useQuery({
    queryKey: ['interview', 'started'],
    queryFn: () => unwrap(api.GET('/api/companies/current/interviews/started')),
    refetchInterval: STARTED_POLL_MS,
  })
}

// 마지막으로 알림을 열어 본 시각. 이 브라우저에만 남긴다. 저장소를 쓸 수 없으면 모두 새 알림으로 본다
const seenKey = (memberId: string) => `hiremate:interview-started-seen:${memberId}`

function readSeen(memberId: string): number {
  try {
    return Number(localStorage.getItem(seenKey(memberId))) || 0
  } catch {
    return 0
  }
}

function writeSeen(memberId: string, at: number) {
  try {
    localStorage.setItem(seenKey(memberId), String(at))
  } catch {
    // 남기지 못해도 이번 화면에서는 읽은 것으로 둔다
  }
}

/**
 * HR 머리글의 알림. 면접관이 모두 준비 완료해 시작한 면접을 알리고, 누르면 그 면접 전형으로 간다.
 * 마지막으로 열어 본 뒤에 시작한 면접이 있으면 종에 점을 찍고, 알림을 닫으면 읽은 것으로 본다.
 */
export function StartedInterviewsBell({ memberId }: { memberId: string }) {
  const started = useStartedInterviews()
  const [seen, setSeen] = useState(() => readSeen(memberId))
  const items = started.data ?? []
  const fresh = (startedAt: string) => Date.parse(startedAt) > seen
  const unread = items.filter((item) => fresh(item.startedAt)).length

  function close() {
    const latest = items[0] ? Date.parse(items[0].startedAt) : 0
    if (latest > seen) {
      writeSeen(memberId, latest)
      setSeen(latest)
    }
  }

  return (
    <Popover onOpenChange={(open) => !open && close()}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={unread > 0 ? `알림 ${unread}개` : '알림'}
          className="relative"
        >
          <Bell />
          {unread > 0 && (
            <span
              aria-hidden="true"
              className="absolute top-1 right-1 size-1.5 rounded-full bg-destructive"
            />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0 text-sm">
        {items.length === 0 ? (
          <p className="p-4 text-muted-foreground">새 알림이 없어요.</p>
        ) : (
          <ul aria-label="시작한 면접" className="max-h-96 divide-y overflow-auto">
            {items.map((item) => (
              <li key={`${item.stageId}:${item.applicationId}`}>
                <Link
                  to={`/hr/recruitments/${item.recruitmentId}/stages/${item.stageId}`}
                  className={cn(
                    'block px-4 py-3 hover:bg-muted/60',
                    fresh(item.startedAt) && 'bg-muted/40',
                  )}
                >
                  <p className="flex items-center gap-1.5 font-medium">
                    {fresh(item.startedAt) && (
                      <span aria-hidden="true" className="size-1.5 rounded-full bg-destructive" />
                    )}
                    {item.applicantName} 면접이 시작됐어요
                  </p>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {item.recruitmentTitle} · {item.stageName} · {formatDateTime(item.startedAt)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  )
}
