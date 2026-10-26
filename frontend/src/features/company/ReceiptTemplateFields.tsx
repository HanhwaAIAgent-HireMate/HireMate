import { Lock } from 'lucide-react'
import { useState } from 'react'

import { useReceiptTemplatePreview } from '@/features/company/api'
import type {
  ReceiptField,
  ReceiptTemplateEditor,
} from '@/features/company/useReceiptTemplateEditor'
import { RECEIPT_VARIABLES } from '@/features/company/variables'
import { VariableField } from '@/features/company/VariableField'
import { MailFrame } from '@/features/notice/MailFrame'

// 접수 확인 메일 양식. 지원서를 내면 바로 자동으로 가는 메일이라 AI 작성 영역 없이 제목과 본문만 있고,
// 저장한 양식으로 만든 예시 메일을 아래에 보여 준다. 모든 공고에 같이 쓰고, 보내는 때의 양식이 나간다
export function ReceiptTemplateFields({ editor }: { editor: ReceiptTemplateEditor }) {
  const preview = useReceiptTemplatePreview()
  // 변수 칩을 누르면 마지막으로 입력하던 칸의 커서 위치에 넣는다
  const [focused, setFocused] = useState<{
    field: ReceiptField
    element: HTMLTextAreaElement | null
  }>({
    field: 'body',
    element: null,
  })
  const { draft, update } = editor
  if (!draft) return null

  const insertVariable = (variable: string) => {
    const { field, element } = focused
    const value = draft[field]
    const start = element?.selectionStart ?? value.length
    const end = element?.selectionEnd ?? value.length
    update({ [field]: value.slice(0, start) + variable + value.slice(end) })
    requestAnimationFrame(() => {
      element?.focus()
      element?.setSelectionRange(start + variable.length, start + variable.length)
    })
  }

  const fieldProps = (field: ReceiptField) => ({
    value: draft[field],
    onChange: (value: string) => update({ [field]: value }),
    onFocus: (element: HTMLTextAreaElement) => setFocused({ field, element }),
  })

  return (
    <>
      <p className="text-sm text-muted-foreground">
        지원서를 내면 바로 자동으로 가는 메일이에요. AI는 쓰지 않고, 모든 공고에 이 양식이 쓰여요.
      </p>
      <div className="space-y-1.5">
        <div className="text-sm font-medium text-muted-foreground">제목</div>
        <VariableField
          aria-label="접수 확인 메일 제목"
          className="rounded-lg border"
          {...fieldProps('subject')}
        />
      </div>
      <div className="space-y-1.5">
        <div className="text-sm font-medium text-muted-foreground">본문</div>
        <VariableField
          aria-label="접수 확인 메일 본문"
          className="rounded-lg border"
          {...fieldProps('body')}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        {RECEIPT_VARIABLES.map((variable) => (
          <button
            key={variable}
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => insertVariable(variable)}
            className="rounded-md bg-ai-soft px-2 py-1 text-xs font-medium text-ai hover:bg-ai/15"
          >
            {variable}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Lock className="size-3.5 shrink-0" />
        필수 문구 고정 · {editor.requiredText}
      </div>
      <div className="space-y-1.5">
        <div className="text-sm font-medium text-muted-foreground">
          미리보기{' '}
          <span className="font-normal">· 저장한 양식이에요. 공고명과 지원자 값은 예시예요</span>
        </div>
        <MailFrame preview={preview.data} title="접수 확인 메일 미리보기" />
      </div>
    </>
  )
}
