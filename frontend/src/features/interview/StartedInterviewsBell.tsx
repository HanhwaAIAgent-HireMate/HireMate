import { useQuery } from '@tanstack/react-query'
import { Bell, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { api, unwrap, type Schemas } from '@/lib/api/client'
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

/** 새로 시작한 면접을 종 아래에 띄워 두는 시간 */
const PREVIEW_MS = 8_000

type StartedInterview = Schemas['StartedInterview']

const stagePath = (item: StartedInterview) =>
  `/hr/recruitments/${item.recruitmentId}/stages/${item.stageId}`

/**
 * HR 머리글의 알림. 면접관이 모두 준비 완료해 시작한 면접을 알리고, 누르면 그 면접 전형으로 간다.
 * 화면을 연 뒤에 새로 시작한 면접은 종 바로 아래에 잠깐 띄워 보여 주고, 마지막으로 열어 본 뒤에 시작한 면접이 있으면
 * 종에 점을 찍는다. 알림을 닫으면 읽은 것으로 본다.
 */
export function StartedInterviewsBell({ memberId }: { memberId: string }) {
  const started = useStartedInterviews()
  const [seen, setSeen] = useState(() => readSeen(memberId))
  // 처음 받아 온 목록의 가장 최근 시작 시각. 이보다 뒤에 시작한 면접이 화면을 연 뒤에 새로 온 알림이다
  const [baseline, setBaseline] = useState<number | null>(null)
  // 띄워 둔 알림을 닫거나 시간이 지나 내린 시각까지는 다시 띄우지 않는다
  const [dismissed, setDismissed] = useState(0)
  const items = started.data ?? []
  const latest = items[0] ? Date.parse(items[0].startedAt) : 0
  if (started.data && baseline === null) setBaseline(latest)
  const fresh = (startedAt: string) => Date.parse(startedAt) > seen
  const unread = items.filter((item) => fresh(item.startedAt)).length
  const shownAfter = Math.max(baseline ?? Infinity, dismissed, seen)
  const arrived = items.filter((item) => Date.parse(item.startedAt) > shownAfter)

  // 띄운 알림만 내린다. 점은 알림 목록을 열어 볼 때까지 남는다
  const dismiss = useCallback(() => setDismissed(latest), [latest])

  function markSeen() {
    if (latest > seen) {
      writeSeen(memberId, latest)
      setSeen(latest)
    }
  }

  return (
    <div className="relative">
      <Popover
        onOpenChange={(open) => {
          if (open) setDismissed(latest)
          else markSeen()
        }}
      >
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
                    to={stagePath(item)}
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
      {arrived.length > 0 && (
        <ArrivedPreview
          key={latest}
          items={arrived}
          onDismiss={dismiss}
          onOpen={() => {
            dismiss()
            markSeen()
          }}
        />
      )}
    </div>
  )
}

/** 오른쪽으로 이만큼 밀면 닫는다 */
const SWIPE_PX = 80

/**
 * 새로 시작한 면접을 종 아래에 띄운 카드. 오른쪽으로 밀거나 ✕로 닫고, 그냥 두면 잠시 뒤 내려간다.
 * 마우스를 올려 두거나 잡고 있는 동안에는 내리지 않는다.
 */
function ArrivedPreview({
  items,
  onDismiss,
  onOpen,
}: {
  items: StartedInterview[]
  onDismiss: () => void
  onOpen: () => void
}) {
  const [offset, setOffset] = useState(0)
  const [held, setHeld] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [dragging, setDragging] = useState(false)
  const drag = useRef<{ startX: number; moved: boolean } | null>(null)
  // 밀어서 놓을 때 이어서 오는 click으로 링크가 열리지 않게 한다
  const dragged = useRef(false)

  useEffect(() => {
    if (held) return
    const timer = setTimeout(onDismiss, PREVIEW_MS)
    return () => clearTimeout(timer)
  }, [held, onDismiss])

  useEffect(() => {
    if (!leaving) return
    const timer = setTimeout(onDismiss, 150)
    return () => clearTimeout(timer)
  }, [leaving, onDismiss])

  function release(clientX: number | null) {
    const current = drag.current
    drag.current = null
    if (!current?.moved) return
    dragged.current = true
    setDragging(false)
    if (clientX !== null && clientX - current.startX > SWIPE_PX) {
      setOffset(360)
      setLeaving(true)
    } else {
      setOffset(0)
      setHeld(false)
    }
  }

  return (
    <div
      role="status"
      aria-label="새 알림"
      title="오른쪽으로 밀어서 닫을 수 있어요"
      style={{ transform: `translateX(${offset}px)`, opacity: Math.max(0.2, 1 - offset / 240) }}
      className={cn(
        'absolute top-full right-0 z-50 mt-2 w-80 animate-in cursor-grab touch-pan-y overflow-hidden rounded-lg border bg-popover text-sm text-popover-foreground shadow-lg fade-in-0 select-none slide-in-from-top-2',
        dragging ? 'cursor-grabbing' : 'transition-[transform,opacity] duration-150',
      )}
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => {
        if (!dragging) setHeld(false)
      }}
      onPointerDown={(event) => {
        if (event.button !== 0) return
        drag.current = { startX: event.clientX, moved: false }
        dragged.current = false
      }}
      onPointerMove={(event) => {
        const current = drag.current
        if (!current) return
        const dx = event.clientX - current.startX
        if (!current.moved && Math.abs(dx) > 5) {
          current.moved = true
          setDragging(true)
          setHeld(true)
          event.currentTarget.setPointerCapture?.(event.pointerId)
        }
        if (current.moved) setOffset(Math.max(0, dx))
      }}
      onPointerUp={(event) => release(event.clientX)}
      onPointerCancel={() => release(null)}
      onClickCapture={(event) => {
        if (dragged.current) {
          dragged.current = false
          event.preventDefault()
          event.stopPropagation()
        }
      }}
    >
      <ul className="divide-y">
        {items.slice(0, 3).map((item) => (
          <li key={`${item.stageId}:${item.applicationId}`}>
            <Link
              to={stagePath(item)}
              draggable={false}
              onClick={onOpen}
              className="flex items-start gap-2.5 px-4 py-3 pr-9 hover:bg-muted/60"
            >
              <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-800">
                <Bell className="size-3.5" />
              </span>
              <span className="min-w-0">
                <span className="block font-medium">{item.applicantName} 면접이 시작됐어요</span>
                <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                  {item.recruitmentTitle} · {item.stageName}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {items.length > 3 && (
        <p className="border-t px-4 py-2 text-xs text-muted-foreground">
          외 {items.length - 3}건은 알림에서 볼 수 있어요.
        </p>
      )}
      <button
        type="button"
        aria-label="새 알림 닫기"
        onClick={onDismiss}
        className="absolute top-2 right-2 rounded-md p-1 text-muted-foreground hover:bg-muted"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}
