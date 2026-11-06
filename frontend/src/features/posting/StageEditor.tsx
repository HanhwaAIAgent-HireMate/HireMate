import { ArrowLeft, ArrowRight, ChevronRight, GripVertical, Plus, X } from 'lucide-react'
import { useState, type DragEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { MAX_STAGES, moveStage, placeStage, type StageForm } from '@/features/posting/stages'
import { STAGE_TYPE_LABELS, type StageType } from '@/features/recruit/labels'
import { cn } from '@/lib/utils'

const TYPES = Object.keys(STAGE_TYPE_LABELS) as StageType[]

/**
 * 전형 절차를 지원자가 볼 흐름 그대로 가로로 보여 주며 HR이 직접 고친다.
 * 전형을 끌어 놓아 순서를 바꾸고 × 로 빼며, 전형을 누르면 이름과 종류를 고친다. 끝의 [전형 추가]로 더한다.
 * 끌 수 없는 사람(키보드, 화면 낭독기, 손 떨림)도 옮길 수 있게 고치는 창에 앞으로 · 뒤로 버튼을 둔다.
 * 맨 앞의 서류 전형은 고정이다. 고치거나 빼거나 옮길 수 없고, 다른 전형도 그 앞으로 옮길 수 없다 (끝의 최종 합격과 같다)
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
  /** 맨 앞이 서류 전형이면 고정한다. 그 뒤의 전형은 1번 자리보다 앞으로 갈 수 없다 */
  const fixedFirst = stages[0]?.type === 'DOCUMENT'
  const firstMovable = fixedFirst ? 1 : 0
  const names = stages.map((stage) => stage.name.trim())
  const change = (index: number, patch: Partial<StageForm>) =>
    onChange(stages.map((stage, i) => (i === index ? { ...stage, ...patch } : stage)))
  /** 끌고 있는 전형과, 놓으면 들어갈 틈(0은 맨 앞, stages.length는 맨 뒤) */
  const [dragging, setDragging] = useState<number | null>(null)
  const [slot, setSlot] = useState<number | null>(null)
  /** 창의 버튼으로 옮긴 방향. 옮긴 전형의 창을 다시 열고 초점을 그 버튼에 둬서 이어서 옮길 수 있게 한다 */
  const [movedBy, setMovedBy] = useState<number | null>(null)
  const open = (index: number | null) => {
    setOpened(index)
    setMovedBy(null)
  }
  const move = (index: number, delta: number) => {
    onChange(moveStage(stages, index, delta))
    setOpened(index + delta)
    setMovedBy(delta)
  }
  /** 같은 방향으로 더 갈 수 없으면 반대 버튼에 초점을 둔다 */
  const focusBack = (index: number) =>
    movedBy === -1 ? index > firstMovable : index === stages.length - 1
  const startDrag = (event: DragEvent, index: number) => {
    open(null)
    setDragging(index)
    event.dataTransfer.effectAllowed = 'move'
    // Firefox는 실을 자료가 없으면 끌기를 시작하지 않는다
    event.dataTransfer.setData('text/plain', String(index))
  }
  /** 전형의 왼쪽 절반 위면 그 앞, 오른쪽 절반 위면 그 뒤 틈에 놓는다. 제자리면 표시하지 않는다 */
  const dragOver = (event: DragEvent, index: number) => {
    if (dragging === null) return
    event.preventDefault()
    const box = event.currentTarget.getBoundingClientRect()
    const next = Math.max(
      firstMovable,
      event.clientX < box.left + box.width / 2 ? index : index + 1,
    )
    setSlot(next === dragging || next === dragging + 1 ? null : next)
  }
  const endDrag = () => {
    setDragging(null)
    setSlot(null)
  }
  const drop = (event: DragEvent) => {
    if (dragging === null || slot === null) return
    event.preventDefault()
    onChange(placeStage(stages, dragging, slot))
    endDrag()
  }
  const remove = (index: number) => {
    open(null)
    onChange(stages.filter((_, i) => i !== index))
  }
  const add = (stage: StageForm) => {
    open(null)
    onChange([...stages, stage])
  }

  return (
    <div className="space-y-2">
      <div
        className="flex flex-wrap items-center gap-1.5"
        onDragOver={(event) => dragging !== null && event.preventDefault()}
        onDrop={drop}
      >
        {stages.map((stage, index) => {
          const label = names[index] || `전형 ${index + 1}`
          const invalid = !names[index] || names.indexOf(names[index]) !== index
          return (
            <span key={index} className="inline-flex items-center gap-1.5">
              {index > 0 && <ChevronRight className="size-3 text-muted-foreground" />}
              {slot === index && <DropMark />}
              {fixedFirst && index === 0 ? (
                <span
                  title="서류 전형은 맨 앞에 고정돼요"
                  className="inline-flex items-center rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground"
                >
                  {names[index] || '서류 전형'}
                  <span className="font-semibold text-ai"> · {STAGE_TYPE_LABELS[stage.type]}</span>
                </span>
              ) : (
                <span
                  draggable
                  onDragStart={(event) => startDrag(event, index)}
                  onDragOver={(event) => dragOver(event, index)}
                  onDragEnd={endDrag}
                  className={cn(
                    'inline-flex items-center rounded-full bg-muted text-xs text-muted-foreground',
                    invalid && 'ring-1 ring-destructive',
                    dragging === index && 'opacity-40',
                  )}
                >
                  <span
                    aria-hidden
                    title="끌어서 순서 바꾸기"
                    className="cursor-grab py-1 pl-1.5 hover:text-foreground active:cursor-grabbing"
                  >
                    <GripVertical className="size-3" />
                  </span>
                  <Popover
                    open={opened === index}
                    onOpenChange={(isOpen) => open(isOpen ? index : null)}
                  >
                    <PopoverTrigger asChild>
                      <button
                        type="button"
                        aria-label={`${label} 고치기`}
                        className="px-1 py-1 hover:text-foreground"
                      >
                        {names[index] || '이름 없음'}
                        <span className="font-semibold text-ai">
                          {' '}
                          · {STAGE_TYPE_LABELS[stage.type]}
                        </span>
                      </button>
                    </PopoverTrigger>
                    <PopoverContent
                      align="start"
                      className="w-64 space-y-3"
                      // 옮겨서 닫힌 창은 초점을 이제 다른 전형이 된 칩으로 돌려보내지 않는다
                      onCloseAutoFocus={(event) => movedBy !== null && event.preventDefault()}
                    >
                      <label className="block space-y-1 text-xs text-muted-foreground">
                        이름
                        <Input
                          autoFocus={movedBy === null}
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
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">순서</p>
                        <div className="flex gap-1.5">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7"
                            aria-label={`${label} 앞으로`}
                            autoFocus={movedBy !== null && focusBack(index)}
                            disabled={index <= firstMovable}
                            onClick={() => move(index, -1)}
                          >
                            <ArrowLeft />
                            앞으로
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7"
                            aria-label={`${label} 뒤로`}
                            autoFocus={movedBy !== null && !focusBack(index)}
                            disabled={index === stages.length - 1}
                            onClick={() => move(index, 1)}
                          >
                            뒤로
                            <ArrowRight />
                          </Button>
                        </div>
                      </div>
                    </PopoverContent>
                  </Popover>
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
              )}
            </span>
          )
        })}
        {slot === stages.length && <DropMark />}
        <ChevronRight className="size-3 text-muted-foreground" />
        <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
          최종 합격
        </span>
        <AddStage names={names} disabled={stages.length >= MAX_STAGES} onAdd={add} />
      </div>
      {problem && <p className="text-xs text-destructive">{problem}</p>}
    </div>
  )
}

/**
 * [전형 추가] 창. 이름과 종류를 고른 뒤 [확인]을 눌러야 최종 합격 앞에 전형이 들어간다.
 * [취소]하거나 창을 닫으면 아무것도 더하지 않는다
 */
function AddStage({
  names,
  disabled,
  onAdd,
}: {
  /** 지금 전형 이름들. 같은 이름은 넣을 수 없다 */
  names: string[]
  disabled: boolean
  onAdd: (stage: StageForm) => void
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [type, setType] = useState<StageType>('INTERVIEW')
  const trimmed = name.trim()
  const problem = !trimmed ? null : names.includes(trimmed) ? '이름이 같은 전형이 있어요.' : null
  const toggle = (next: boolean) => {
    if (next) {
      setName('')
      setType('INTERVIEW')
    }
    setOpen(next)
  }
  const confirm = () => {
    if (!trimmed || problem) return
    onAdd({ name: trimmed, type, icon: null })
    setOpen(false)
  }
  return (
    <Popover open={open} onOpenChange={toggle}>
      <PopoverTrigger asChild>
        <Button size="sm" variant="outline" className="ml-1 h-7" disabled={disabled}>
          <Plus />
          전형 추가
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 space-y-3">
        <label className="block space-y-1 text-xs text-muted-foreground">
          이름
          <Input
            autoFocus
            aria-label="새 전형 이름"
            value={name}
            maxLength={50}
            placeholder="예: 2차 면접"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
                event.preventDefault()
                confirm()
              }
            }}
            className="h-8 text-sm text-foreground"
          />
        </label>
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">종류</p>
          <div role="radiogroup" aria-label="새 전형 종류" className="flex gap-1.5">
            {TYPES.map((item) => (
              <button
                key={item}
                type="button"
                role="radio"
                aria-checked={type === item}
                onClick={() => setType(item)}
                className={cn(
                  'rounded-md border px-2.5 py-1 text-xs',
                  type === item ? 'border-foreground font-semibold' : 'text-muted-foreground',
                )}
              >
                {STAGE_TYPE_LABELS[item]}
              </button>
            ))}
          </div>
        </div>
        {problem && <p className="text-xs text-destructive">{problem}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => setOpen(false)}>
            취소
          </Button>
          <Button type="button" size="sm" disabled={!trimmed || Boolean(problem)} onClick={confirm}>
            확인
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

/** 끌고 있는 전형이 들어갈 자리 */
function DropMark() {
  return <span aria-hidden className="h-5 w-0.5 rounded-full bg-foreground" />
}
