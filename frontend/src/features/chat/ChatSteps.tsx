import { ChevronRight, CornerDownRight } from 'lucide-react'
import { useEffect, useId, useState } from 'react'

import {
  durationLabel,
  rootStepCount,
  stepTree,
  type ChatStep,
  type StepNode,
} from '@/features/chat/steps'
import { cn } from '@/lib/utils'

/**
 * 답을 기다리는 동안의 처리 과정. Root 단계를 세로선 위의 점으로 쌓고, 지금 단계 아래에는 하는 일 한 줄만 보인다.
 * 걸린 시간은 이 표시가 나타난 때(질문을 보낸 때)부터 센다.
 */
export function LiveSteps({ steps }: { steps: ChatStep[] }) {
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
 * 답을 낸 처리 과정. 한 줄 요약(Root 단계 수)으로 접어 두고 누르면 하위 일까지 펼친다. 방금 받은 답과 다시 불러온 대화 기록이 같이 쓴다.
 * 단계가 없으면(이 기능 전의 기록) 아무것도 그리지 않는다.
 */
export function StepsSummary({ steps, seconds }: { steps: ChatStep[]; seconds: number | null }) {
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
        처리 과정 {rootStepCount(steps)}단계
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

/**
 * Root 단계를 세로선 위의 점으로 잇는 목록. 끝난 단계는 초록 점, 지금 단계는 깜빡이는 회색 점이다.
 * 하위 Agent와 도구의 일은 깊이와 상관없이 Root 단계 아래 한 칸만 들여 쓴다.
 * running이면 마지막 Root 단계가 지금 단계이고 그 아래에는 지금 하는 일만 보인다. 아니면 모든 일을 보인다.
 */
function StepList({ steps, running = false }: { steps: ChatStep[]; running?: boolean }) {
  const tree = stepTree(steps)
  return (
    <ol className="relative space-y-2">
      {tree.length > 1 && (
        <span aria-hidden className="absolute top-2 bottom-2 left-[4px] w-px bg-border" />
      )}
      {tree.map((node, index) => {
        const current = running && index === tree.length - 1
        return (
          <li
            key={node.index}
            data-testid="root-step"
            aria-current={current ? 'step' : undefined}
            className={cn(
              'relative pl-5 text-[13px] leading-5',
              current ? 'text-foreground' : 'text-muted-foreground',
            )}
          >
            <span
              aria-hidden
              data-dot={current ? 'running' : 'done'}
              className={cn(
                'absolute top-1.5 left-0 size-2.5 rounded-full',
                current ? 'animate-pulse bg-muted-foreground/60' : 'bg-emerald-500',
              )}
            />
            <span data-step-text>{node.step.text}</span>
            {current ? (
              <CurrentWork works={node.children} />
            ) : (
              !running && <AllWork works={node.children} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

/** 지금 단계 아래의 일. 가장 최근 일과 그 결과만 보이고, 앞선 일은 개수로 접는다 */
function CurrentWork({ works }: { works: StepNode[] }) {
  const latest = works.at(-1)
  if (!latest) return null
  return (
    <ol className="mt-1 space-y-0.5 text-xs leading-4">
      {works.length > 1 && (
        <li className="text-muted-foreground">앞서 한 일 {works.length - 1}개</li>
      )}
      {flatten([latest]).map((line) => (
        <WorkLine key={line.index} line={line} />
      ))}
    </ol>
  )
}

/** 끝난 단계 아래의 모든 일과 결과 */
function AllWork({ works }: { works: StepNode[] }) {
  if (works.length === 0) return null
  return (
    <ol className="mt-1 space-y-0.5 text-xs leading-4 text-muted-foreground">
      {flatten(works).map((line) => (
        <WorkLine key={line.index} line={line} />
      ))}
    </ol>
  )
}

type Line = { step: ChatStep; index: number; result: boolean }

/** 일과 그 아래 결과를 받은 순서로 편다. 일(depth 1) 아래에 온 단계는 모두 결과로 본다 */
function flatten(nodes: StepNode[], result = false): Line[] {
  return nodes.flatMap((node) => [
    { step: node.step, index: node.index, result },
    ...flatten(node.children, true),
  ])
}

function WorkLine({ line }: { line: Line }) {
  return (
    <li data-testid="sub-step" className={cn('flex items-start gap-1', line.result && 'pl-1')}>
      {line.result && <CornerDownRight aria-hidden className="mt-px size-3 shrink-0" />}
      <span>
        <StepText text={line.step.text} />
      </span>
    </li>
  )
}

/** 하위 Agent의 일("서류 Agent · …")은 Agent 이름을 칩으로 보인다. 문구 형식은 ai 서버의 코드 상수다 */
function StepText({ text }: { text: string }) {
  const agent = /^(.+ Agent) · (.+)$/.exec(text)
  if (!agent) return text
  return (
    <>
      <span data-agent className="mr-1 rounded bg-ai-soft px-1 py-px text-[11px] text-ai">
        {agent[1]}
      </span>
      {agent[2]}
    </>
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
