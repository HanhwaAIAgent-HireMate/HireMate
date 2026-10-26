import { useState } from 'react'
import { toast } from 'sonner'

import { useReceiptTemplate, useSaveReceiptTemplate } from '@/features/company/api'
import { errorMessage } from '@/lib/api/client'

export type ReceiptField = 'subject' | 'body'

/** 설정 › 안내 메일의 [접수 확인] 탭 상태. 저장 버튼이 설정 칸 위에 하나라 안내 메일 양식이 이 상태로 저장한다 */
export function useReceiptTemplateEditor() {
  const template = useReceiptTemplate()
  const save = useSaveReceiptTemplate()
  // 저장 전 고친 내용. 저장하면 지우고 서버 값을 다시 쓴다
  const [edit, setEdit] = useState<{ subject: string; body: string } | null>(null)
  const draft = edit ?? template.data
  const update = (patch: Partial<Record<ReceiptField, string>>) => {
    if (draft) setEdit({ subject: draft.subject, body: draft.body, ...patch })
  }
  const onSave = () => {
    if (!draft) return
    if (!draft.subject.trim() || !draft.body.trim()) {
      toast.error('접수 확인 메일의 제목과 본문을 입력해 주세요.')
      return
    }
    save.mutate(
      { subject: draft.subject, body: draft.body },
      {
        onSuccess: () => {
          setEdit(null)
          toast.success('접수 확인 메일 양식을 저장했어요.')
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }
  return {
    draft,
    requiredText: template.data?.requiredText ?? '',
    update,
    onSave,
    saving: save.isPending,
  }
}

export type ReceiptTemplateEditor = ReturnType<typeof useReceiptTemplateEditor>
