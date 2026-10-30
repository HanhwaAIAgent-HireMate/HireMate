import { zodResolver } from '@hookform/resolvers/zod'
import { ChevronRight, Lock, X } from 'lucide-react'
import { useEffect } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Textarea } from '@/components/ui/textarea'
import { usePostingSettings, useSavePostingSettings } from '@/features/company/api'
import { AddButton } from '@/features/company/CompanyProfileForm'
import { SettingsRow, SettingsSection } from '@/features/company/SettingsSection'
import { errorMessage } from '@/lib/api/client'

// 공고에서 HR 요청으로만 바뀌는 고정 칸
const FIXED_SECTIONS = new Set(['전형 절차', '필수 제출 서류', '유의사항'])

const schema = z.object({
  writingStyle: z.string().max(1000),
  requiredNotices: z.array(z.object({ value: z.string().trim().min(1).max(200) })).max(10),
})

type Values = z.infer<typeof schema>

// CMP-02. 새 공고는 이 Template 순서로 열리고, Posting Agent는 작성 스타일을 따른다
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
      <SettingsRow label="공고 Template">
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {(settings.data?.sections ?? []).map((section, index) => (
            <span key={section} className="inline-flex items-center gap-1.5">
              {index > 0 && <ChevronRight className="size-3 text-muted-foreground" />}
              <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                {FIXED_SECTIONS.has(section) && <Lock className="size-3" />}
                {section}
              </span>
            </span>
          ))}
        </div>
      </SettingsRow>
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
