import { Lock, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'
import {
  useNoticeTemplates,
  useSaveNoticeTemplate,
  type NoticeTemplate,
  type NoticeTemplateType,
} from '@/features/company/api'
import { SettingsSection } from '@/features/company/SettingsSection'
import { NOTICE_TYPE_LABELS, NOTICE_VARIABLES } from '@/features/company/variables'
import { VariableField } from '@/features/company/VariableField'
import { errorMessage } from '@/lib/api/client'

type Field = 'subject' | 'greeting' | 'closing'

// CMP-03. 안내 초안은 이 양식으로 만들어지고, Communication Agent는 AI 작성 영역만 쓴다
export function NoticeTemplateForm() {
  const templates = useNoticeTemplates()
  const save = useSaveNoticeTemplate()
  const [type, setType] = useState<NoticeTemplateType>('NEXT_STAGE')
  // 저장 전 고친 내용. 저장하면 지우고 서버 값을 다시 쓴다
  const [edits, setEdits] = useState<Partial<Record<NoticeTemplateType, NoticeTemplate>>>({})
  // 변수 칩을 누르면 마지막으로 입력하던 칸의 커서 위치에 넣는다
  const [focused, setFocused] = useState<{ field: Field; element: HTMLTextAreaElement | null }>({
    field: 'greeting',
    element: null,
  })

  const draft = edits[type] ?? templates.data?.find((template) => template.type === type)
  const update = (patch: Partial<NoticeTemplate>) => {
    if (draft) setEdits((current) => ({ ...current, [type]: { ...draft, ...patch } }))
  }

  const insertVariable = (variable: string) => {
    if (!draft) return
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

  const onSave = () => {
    if (!draft) return
    if (!draft.subject.trim()) {
      toast.error('제목을 입력해 주세요.')
      return
    }
    save.mutate(draft, {
      onSuccess: () => {
        setEdits((current) => {
          const next = { ...current }
          delete next[type]
          return next
        })
        toast.success(`${NOTICE_TYPE_LABELS[type]} 양식을 저장했어요.`)
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const fieldProps = (field: Field) => ({
    value: draft?.[field] ?? '',
    onChange: (value: string) => update({ [field]: value }),
    onFocus: (element: HTMLTextAreaElement) => setFocused({ field, element }),
  })

  return (
    <SettingsSection title="안내 메일" saving={save.isPending} onSave={onSave}>
      <div role="tablist" className="inline-flex gap-1 rounded-lg border p-1">
        {(Object.keys(NOTICE_TYPE_LABELS) as NoticeTemplateType[]).map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={key === type}
            onClick={() => setType(key)}
            className={cn(
              'rounded-md px-3 py-1 text-sm',
              key === type
                ? 'bg-foreground font-medium text-background'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {NOTICE_TYPE_LABELS[key]}
          </button>
        ))}
      </div>
      {draft && (
        <>
          <div className="space-y-1.5">
            <div className="text-sm font-medium text-muted-foreground">제목</div>
            <VariableField
              aria-label="제목"
              className="rounded-lg border"
              {...fieldProps('subject')}
            />
          </div>
          <div className="space-y-1.5">
            <div className="text-sm font-medium text-muted-foreground">본문</div>
            <div className="space-y-1 rounded-lg border p-1">
              <VariableField aria-label="인사말" placeholder="인사말" {...fieldProps('greeting')} />
              <div className="mx-2 flex items-center gap-2 rounded-lg border border-dashed border-ai/60 bg-ai-soft/60 px-3 py-2.5 text-sm">
                <Sparkles className="size-4 text-ai" />
                <span className="font-semibold text-ai">AI 작성 영역</span>
                <input
                  aria-label="AI 작성 영역 안내"
                  value={draft.aiGuide}
                  onChange={(event) => update({ aiGuide: event.target.value })}
                  className="min-w-0 flex-1 bg-transparent text-xs text-muted-foreground outline-none"
                />
              </div>
              <VariableField aria-label="맺음말" placeholder="맺음말" {...fieldProps('closing')} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {NOTICE_VARIABLES.map((variable) => (
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
            <span className="shrink-0">필수 문구 고정 ·</span>
            <input
              aria-label="필수 문구"
              value={draft.requiredText}
              onChange={(event) => update({ requiredText: event.target.value })}
              className="min-w-0 flex-1 bg-transparent outline-none focus:text-foreground"
            />
          </div>
        </>
      )}
    </SettingsSection>
  )
}
