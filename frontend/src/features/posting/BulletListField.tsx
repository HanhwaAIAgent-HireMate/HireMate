import { useRef } from 'react'

import { cn } from '@/lib/utils'

/**
 * 한 줄에 한 항목을 쓰는 목록 입력. Enter로 줄을 나누고 빈 줄에서 Backspace로 지운다.
 * highlight에 있는 줄은 AI 수정안으로 바뀐 줄로 표시한다.
 */
export function BulletListField({
  label,
  items,
  onChange,
  disabled,
  highlight,
  placeholder = '내용을 입력해 주세요',
}: {
  label: string
  items: string[]
  onChange: (items: string[]) => void
  disabled?: boolean
  highlight?: Set<string>
  placeholder?: string
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
          )}
        >
          <span className="text-muted-foreground">·</span>
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
        </div>
      ))}
    </div>
  )
}
