import { useRef } from 'react'

import { cn } from '@/lib/utils'

/**
 * 한 줄에 한 항목을 쓰는 목록 입력. Enter로 줄을 나누고 빈 줄에서 Backspace로 지운다.
 * highlight에 있는 줄은 AI 수정안으로 바뀐 줄로 표시한다.
 * onSelect가 있으면 줄 앞의 ·을 눌러 AI에게 맡길 줄을 고른다. 빈 줄은 고를 수 없다.
 * onMark가 있으면 줄 끝의 [필수]로 서류 필수 조건을 켜고 끈다. marked에 있는 줄이 켜진 줄이다.
 */
export function BulletListField({
  label,
  items,
  onChange,
  disabled,
  highlight,
  placeholder = '내용을 입력해 주세요',
  selected,
  onSelect,
  marked,
  onMark,
}: {
  label: string
  items: string[]
  onChange: (items: string[]) => void
  disabled?: boolean
  highlight?: Set<string>
  placeholder?: string
  selected?: number
  onSelect?: (index: number) => void
  marked?: Set<string>
  onMark?: (index: number) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const rows = items.length === 0 ? [''] : items

  const focusRow = (index: number) =>
    requestAnimationFrame(() => {
      const inputs = container.current?.querySelectorAll('input')
      inputs?.[index]?.focus()
    })

  const update = (index: number, value: string) =>
    onChange(rows.map((row, i) => (i === index ? value : row)))

  return (
    <div ref={container} className="space-y-0.5">
      {rows.map((row, index) => (
        <div
          key={index}
          className={cn(
            'flex items-baseline gap-2 rounded px-1 text-sm',
            highlight?.has(row) && 'bg-pass',
            selected === index && 'bg-ai-soft ring-1 ring-ai/40',
          )}
        >
          <LineBullet
            label={`${label} ${index + 1}번`}
            selected={selected === index}
            onSelect={onSelect && !disabled && row.trim() ? () => onSelect(index) : undefined}
          />
          <input
            aria-label={`${label} ${index + 1}`}
            value={row}
            disabled={disabled}
            placeholder={index === 0 ? placeholder : undefined}
            onChange={(event) => update(index, event.target.value)}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return
              if (event.key === 'Enter') {
                event.preventDefault()
                onChange([...rows.slice(0, index + 1), '', ...rows.slice(index + 1)])
                focusRow(index + 1)
              } else if (event.key === 'Backspace' && row === '' && rows.length > 1) {
                event.preventDefault()
                onChange(rows.filter((_, i) => i !== index))
                focusRow(Math.max(0, index - 1))
              }
            }}
            className="min-w-0 flex-1 bg-transparent py-1 outline-none placeholder:text-muted-foreground disabled:cursor-default"
          />
          {onMark && row.trim() && (
            <RequiredToggle
              label={`${label} ${index + 1}번`}
              on={marked?.has(row) ?? false}
              disabled={disabled}
              onToggle={() => onMark(index)}
            />
          )}
        </div>
      ))}
    </div>
  )
}

/** 줄 앞의 ·. onSelect가 있으면 눌러서 AI에게 맡길 줄로 고르고, 다시 누르면 풀린다 */
export function LineBullet({
  label,
  selected,
  onSelect,
}: {
  label: string
  selected?: boolean
  onSelect?: () => void
}) {
  if (!onSelect) return <span className="px-1 text-muted-foreground">·</span>
  return (
    <button
      type="button"
      aria-label={`${label} 고르기`}
      aria-pressed={selected}
      title={selected ? '다시 누르면 풀려요' : '이 줄만 AI에게 고쳐 달라고 할 때 눌러요'}
      onClick={onSelect}
      className={cn(
        'rounded px-1 text-muted-foreground hover:bg-ai-soft hover:text-ai',
        selected && 'font-bold text-ai',
      )}
    >
      ·
    </button>
  )
}

/** 서류 필수 조건 표시. 모든 줄에 보이고, 켜진 줄은 검은 바탕으로 구분한다 */
function RequiredToggle({
  label,
  on,
  disabled,
  onToggle,
}: {
  label: string
  on: boolean
  disabled?: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={`${label} 서류 필수 조건`}
      title={
        on ? '서류 필수 조건이에요. 지원자에게는 보이지 않아요' : '서류 필수 조건으로 표시해요'
      }
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        'shrink-0 self-center rounded px-1.5 py-0.5 text-[11px] font-medium',
        on
          ? 'bg-foreground text-background'
          : 'border text-muted-foreground hover:bg-muted hover:text-foreground',
        disabled && 'cursor-default',
      )}
    >
      필수
    </button>
  )
}
