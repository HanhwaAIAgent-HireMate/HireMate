import { renderVariables } from '@/features/company/variables'
import { cn } from '@/lib/utils'

type Props = {
  value: string
  onChange: (value: string) => void
  onFocus?: (element: HTMLTextAreaElement) => void
  className?: string
  placeholder?: string
  'aria-label'?: string
}

/**
 * 변수를 강조해 보여 주는 입력칸. 같은 글꼴과 여백의 강조 레이어 위에 글자가 투명한 textarea를 겹친다.
 * 줄 수만큼 높이가 늘어나 스크롤이 생기지 않는다.
 */
export function VariableField({
  value,
  onChange,
  onFocus,
  className,
  placeholder,
  ...rest
}: Props) {
  const shared = 'px-3 py-2 text-sm leading-6 whitespace-pre-wrap break-words'
  return (
    <div className={cn('relative', className)}>
      <div aria-hidden className={cn(shared, 'pointer-events-none min-h-10')}>
        {renderVariables(value)}
        {value.endsWith('\n') || value === '' ? ' ' : null}
      </div>
      <textarea
        value={value}
        rows={1}
        placeholder={placeholder}
        aria-label={rest['aria-label']}
        onFocus={(event) => onFocus?.(event.currentTarget)}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          shared,
          'absolute inset-0 resize-none overflow-hidden bg-transparent text-transparent caret-foreground outline-none placeholder:text-muted-foreground',
        )}
      />
    </div>
  )
}
