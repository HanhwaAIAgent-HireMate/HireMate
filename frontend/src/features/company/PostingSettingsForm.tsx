import { zodResolver } from '@hookform/resolvers/zod'
import { Lock, X } from 'lucide-react'
import { useEffect } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Textarea } from '@/components/ui/textarea'
import { usePostingSettings, useSavePostingSettings } from '@/features/company/api'
import { AddButton } from '@/features/company/CompanyProfileForm'
import { SettingsRow, SettingsSection } from '@/features/company/SettingsSection'
import { errorMessage } from '@/lib/api/client'

const schema = z.object({
  writingStyle: z.string().max(1000),
  requiredNotices: z.array(z.object({ value: z.string().trim().min(1).max(200) })).max(10),
})

type Values = z.infer<typeof schema>

// CMP-02. Posting Agent는 작성 스타일을 따르고, 모든 공고에 필수 안내 문구가 들어간다
export function PostingSettingsForm() {
  const settings = usePostingSettings()
  const save = useSavePostingSettings()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { writingStyle: '', requiredNotices: [] },
  })
  const notices = useFieldArray({ control: form.control, name: 'requiredNotices' })

  useEffect(() => {
    if (!settings.data) return
    form.reset({
      writingStyle: settings.data.writingStyle,
      requiredNotices: settings.data.requiredNotices.map((value) => ({ value })),
    })
  }, [settings.data, form])

  const onSave = form.handleSubmit(
    (values) =>
      save.mutate(
        {
          writingStyle: values.writingStyle,
          requiredNotices: values.requiredNotices.map((notice) => notice.value),
        },
        {
          onSuccess: () => toast.success('채용 공고 설정을 저장했어요.'),
          onError: (error) => toast.error(errorMessage(error)),
        },
      ),
    () => toast.error('비어 있는 필수 안내 문구를 채우거나 지워 주세요.'),
  )

  return (
    <SettingsSection title="채용 공고" saving={save.isPending} onSave={() => void onSave()}>
      <SettingsRow label="작성 스타일">
        <Textarea
          rows={2}
          placeholder="예: 짧고 친근한 존댓말로 써요. 과장 없이 실제 업무를 구체적으로 적어요."
          {...form.register('writingStyle')}
        />
      </SettingsRow>
      <SettingsRow label="필수 안내 문구">
        <div className="space-y-2">
          {notices.fields.map((field, index) => (
            <div
              key={field.id}
              className="group flex items-center gap-2 rounded-lg border bg-muted/40 px-3 py-1.5"
            >
              <Lock className="size-3.5 shrink-0 text-muted-foreground" />
              <input
                aria-label={`필수 안내 문구 ${index + 1}`}
                className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                {...form.register(`requiredNotices.${index}.value`)}
              />
              <button
                type="button"
                aria-label="문구 삭제"
                className="invisible text-muted-foreground group-hover:visible hover:text-foreground"
                onClick={() => notices.remove(index)}
              >
                <X className="size-3.5" />
              </button>
            </div>
          ))}
          {notices.fields.length < 10 && (
            <AddButton onClick={() => notices.append({ value: '' })}>문구 추가</AddButton>
          )}
        </div>
      </SettingsRow>
    </SettingsSection>
  )
}
