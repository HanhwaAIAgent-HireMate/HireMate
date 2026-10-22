import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { GuideField } from '@/features/notice/guide'

// 전형별 안내 · 입사 안내의 입력 칸. 칸 이름을 왼쪽에 두고 한 줄씩 늘어놓는다
export function GuideFields<K extends string>({
  name,
  fields,
  values,
  disabled,
  onChange,
}: {
  /** 화면 읽기 프로그램에 읽히는 칸 이름 앞부분 (예: 코딩테스트) */
  name: string
  fields: GuideField<K>[]
  values: Record<K, string>
  disabled: boolean
  onChange: (key: K, value: string) => void
}) {
  return fields.map((field) => {
    const props = {
      'aria-label': `${name} ${field.label}`,
      value: values[field.key],
      placeholder: field.placeholder,
      maxLength: field.maxLength,
      disabled,
      onChange: (event: { target: { value: string } }) => onChange(field.key, event.target.value),
    }
    return (
      <label key={field.key} className="grid grid-cols-[96px_1fr] items-start gap-2">
        <span className="pt-1.5 text-xs text-muted-foreground">
          {field.label}
          {field.optional && <span className="ml-1 text-[11px]">(선택)</span>}
        </span>
        {field.optional ? (
          <Textarea {...props} rows={2} className="min-h-0" />
        ) : (
          <Input {...props} />
        )}
      </label>
    )
  })
}
