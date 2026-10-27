import { Check, ChevronRight, LoaderCircle } from 'lucide-react'
import { useEffect, useId, useState } from 'react'

import { durationLabel } from '@/features/chat/steps'
import { cn } from '@/lib/utils'

/**
 * 답을 기다리는 동안의 처리 과정. 지난 단계는 체크로 쌓고 지금 단계는 돌아가는 표시와 함께 맨 아래에 둔다.
 * 걸린 시간은 이 표시가 나타난 때(질문을 보낸 때)부터 센다.
 */
export function LiveSteps({ steps }: { steps: string[] }) {
  const seconds = useElapsed()
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        처리 중<span aria-hidden>·</span>
        <span className="tabular-nums">{durationLabel(seconds)}</span>
      </div>
      {/* 1초마다 바뀌는 시간은 빼고 새로 쌓인 단계만 읽어 준다 */}
      <div aria-live="polite">
        <StepList steps={steps} running />
      </div>
    </div>
  )
}

/**
 * 답을 낸 처리 과정. 한 줄 요약으로 접어 두고 누르면 단계 전체를 펼친다. 방금 받은 답과 다시 불러온 대화 기록이 같이 쓴다.
 * 단계가 없으면(이 기능 전의 기록) 아무것도 그리지 않는다.
 */
export function StepsSummary({ steps, seconds }: { steps: string[]; seconds: number | null }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  if (steps.length === 0) return null
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"
      >
        처리 과정 {steps.length}단계
        {seconds !== null && <span className="tabular-nums"> · {durationLabel(seconds)}</span>}
        <ChevronRight className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
      </button>
      {open && (
        <div id={id} className="mt-1.5">
          <StepList steps={steps} />
        </div>
      )}
    </div>
  )
}

/** 세로선으로 이은 단계 목록. running이면 마지막 단계가 지금 하는 일이다. */
function StepList({ steps, running = false }: { steps: string[]; running?: boolean }) {
  return (
    <ol className="space-y-1">
      {steps.map((step, index) => {
        const current = running && index === steps.length - 1
        return (
          <li
            key={index}
            aria-current={current ? 'step' : undefined}
            className={cn(
              'relative flex items-start gap-2 text-[13px] leading-5',
              current ? 'text-foreground' : 'text-muted-foreground',
            )}
          >
            {index < steps.length - 1 && (
              <span
                aria-hidden
                className="absolute top-5 bottom-[-0.25rem] left-[7px] w-px bg-border"
              />
            )}
            {current ? (
              <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin text-ai" />
            ) : (
              <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full bg-muted">
                <Check className="size-2.5" />
              </span>
            )}
            <span>{step}</span>
          </li>
        )
      })}
    </ol>
  )
}

/** 처음 그린 때부터 지난 초. 1초마다 다시 그린다. */
function useElapsed(): number {
  const [startedAt] = useState(() => Date.now())
  const [now, setNow] = useState(startedAt)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return Math.max(0, Math.floor((now - startedAt) / 1000))
}
