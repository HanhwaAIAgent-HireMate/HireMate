import { ArrowLeft, ArrowRight, ChevronRight, Plus, X } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { MAX_STAGES, moveStage, type StageForm } from '@/features/posting/stages'
import { STAGE_TYPE_LABELS, type StageType } from '@/features/recruit/labels'
import { StageIcon } from '@/features/recruit/StageIcon'
import { STAGE_ICONS } from '@/features/recruit/stage-icons'
import { cn } from '@/lib/utils'

const TYPES = Object.keys(STAGE_TYPE_LABELS) as StageType[]

/**
 * 전형 절차를 지원자가 볼 흐름 그대로 가로로 보여 주며 HR이 직접 고친다.
 * ← → 로 순서를 바꾸고 × 로 빼며, 전형을 누르면 이름과 종류를 고친다. 끝의 [전형 추가]로 더한다
 */
export function StageEditor({
  stages,
  onChange,
  problem,
}: {
  stages: StageForm[]
  onChange: (stages: StageForm[]) => void
  /** 저장하려다 막힌 이유 */
  problem: string | null
}) {
  const [opened, setOpened] = useState<number | null>(null)
  const names = stages.map((stage) => stage.name.trim())
  const change = (index: number, patch: Partial<StageForm>) =>
    onChange(stages.map((stage, i) => (i === index ? { ...stage, ...patch } : stage)))
  const move = (index: number, delta: number) => {
    setOpened(null)
    onChange(moveStage(stages, index, delta))
  }
  const remove = (index: number) => {
    setOpened(null)
    onChange(stages.filter((_, i) => i !== index))
  }
  const add = () => {
    onChange([...stages, { name: '', type: 'INTERVIEW' }])
    setOpened(stages.length)
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {stages.map((stage, index) => {
          const label = names[index] || `전형 ${index + 1}`
          const invalid = !names[index] || names.indexOf(names[index]) !== index
          return (
            <span key={index} className="inline-flex items-center gap-1.5">
              {index > 0 && <ChevronRight className="size-3 text-muted-foreground" />}
              <span
                className={cn(
                  'inline-flex items-center rounded-full bg-muted text-xs text-muted-foreground',
                  invalid && 'ring-1 ring-destructive',
                )}
              >
                <button
                  type="button"
                  aria-label={`${label} 앞으로`}
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                  className="rounded-l-full py-1 pr-0.5 pl-2 hover:text-foreground disabled:opacity-30"
                >
                  <ArrowLeft className="size-3" />
                </button>
                <Popover
                  open={opened === index}
                  onOpenChange={(open) => setOpened(open ? index : null)}
                >
                  <PopoverTrigger asChild>
                    <button
                      type="button"
                      aria-label={`${label} 고치기`}
                      className="inline-flex items-center gap-1 px-1 py-1 hover:text-foreground"
                    >
                      <StageIcon type={stage.type} icon={stage.icon} />
                      {names[index] || '이름 없음'}
                      <span className="font-semibold text-ai">
                        {' '}
                        · {STAGE_TYPE_LABELS[stage.type]}
                      </span>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="w-72 space-y-3">
                    <label className="block space-y-1 text-xs text-muted-foreground">
                      이름
                      <Input
                        autoFocus
                        aria-label="전형 이름"
                        value={stage.name}
                        maxLength={50}
                        placeholder="예: 1차 면접"
                        onChange={(event) => change(index, { name: event.target.value })}
                        className="h-8 text-sm text-foreground"
                      />
                    </label>
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">종류</p>
                      <div role="radiogroup" aria-label="전형 종류" className="flex gap-1.5">
                        {TYPES.map((type) => (
                          <button
                            key={type}
                            type="button"
                            role="radio"
                            aria-checked={stage.type === type}
                            onClick={() => change(index, { type })}
                            className={cn(
                              'rounded-md border px-2.5 py-1 text-xs',
                              stage.type === type
                                ? 'border-foreground font-semibold'
                                : 'text-muted-foreground',
                            )}
                          >
                            {STAGE_TYPE_LABELS[type]}
                          </button>
                        ))}
                      </div>
                    </div>
                    <fieldset className="space-y-2">
                      <legend className="text-xs text-muted-foreground">아이콘</legend>
                      <div className="grid grid-cols-5 gap-1.5">
                        {STAGE_ICONS.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            aria-label={`아이콘: ${item.label}`}
                            aria-pressed={(stage.icon ?? 'AUTO') === item.id}
                            onClick={() => change(index, { icon: item.id })}
                            className={cn(
                              'flex flex-col items-center gap-1 rounded-md border px-1 py-2 text-[10px]',
                              (stage.icon ?? 'AUTO') === item.id
                                ? 'border-foreground bg-muted font-semibold'
                                : 'text-muted-foreground hover:bg-muted',
                            )}
                          >
                            {item.id === 'NONE' ? (
                              <X className="size-4" aria-hidden="true" />
                            ) : (
                              <StageIcon type={stage.type} icon={item.id} className="size-4" />
                            )}
                            {item.label}
                          </button>
                        ))}
                      </div>
                    </fieldset>
                  </PopoverContent>
                </Popover>
                <button
                  type="button"
                  aria-label={`${label} 뒤로`}
                  disabled={index === stages.length - 1}
                  onClick={() => move(index, 1)}
                  className="py-1 pr-1 pl-0.5 hover:text-foreground disabled:opacity-30"
                >
                  <ArrowRight className="size-3" />
                </button>
                <button
                  type="button"
                  aria-label={`${label} 빼기`}
                  disabled={stages.length === 1}
                  onClick={() => remove(index)}
                  className="rounded-r-full py-1 pr-2 pl-0.5 hover:text-foreground disabled:opacity-30"
                >
                  <X className="size-3" />
                </button>
              </span>
            </span>
          )
        })}
        <ChevronRight className="size-3 text-muted-foreground" />
        <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
          최종 합격
        </span>
        <Button
          size="sm"
          variant="outline"
          className="ml-1 h-7"
          onClick={add}
          disabled={stages.length >= MAX_STAGES}
        >
          <Plus />
          전형 추가
        </Button>
      </div>
      {problem && <p className="text-xs text-destructive">{problem}</p>}
    </div>
  )
}
