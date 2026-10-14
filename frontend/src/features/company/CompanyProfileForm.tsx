import { zodResolver } from '@hookform/resolvers/zod'
import { Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Textarea } from '@/components/ui/textarea'
import { useCompanyProfile, useSaveCompanyProfile } from '@/features/company/api'
import { ReferenceFiles } from '@/features/company/ReferenceFiles'
import { SettingsRow, SettingsSection } from '@/features/company/SettingsSection'
import { errorMessage } from '@/lib/api/client'

const schema = z.object({
  intro: z.string().max(5000),
  culture: z.string().max(5000),
  talents: z
    .array(z.object({ title: z.string().trim().min(1).max(50), description: z.string().max(200) }))
    .max(10),
  benefits: z.array(z.object({ value: z.string().trim().min(1).max(30) })).max(20),
})

type Values = z.infer<typeof schema>

// CMP-01. 회사 소개 · 조직 문화 · 인재상 · 복지는 공고의 회사 소개 · 복지와 AI의 인재상 판단 기준이 된다
export function CompanyProfileForm() {
  const profile = useCompanyProfile()
  const save = useSaveCompanyProfile()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { intro: '', culture: '', talents: [], benefits: [] },
  })
  const talents = useFieldArray({ control: form.control, name: 'talents' })
  const benefits = useFieldArray({ control: form.control, name: 'benefits' })
  const [benefitDraft, setBenefitDraft] = useState('')

  useEffect(() => {
    if (!profile.data) return
    form.reset({
      intro: profile.data.intro,
      culture: profile.data.culture,
      talents: profile.data.talents,
      benefits: profile.data.benefits.map((value) => ({ value })),
    })
  }, [profile.data, form])

  const onSave = form.handleSubmit(
    (values) =>
      save.mutate(
        { ...values, benefits: values.benefits.map((benefit) => benefit.value) },
        {
          onSuccess: () => toast.success('회사 소개를 저장했어요.'),
          onError: (error) => toast.error(errorMessage(error)),
        },
      ),
    () => toast.error('비어 있는 인재상이나 복지 항목을 채우거나 지워 주세요.'),
  )

  const addBenefit = () => {
    const value = benefitDraft.trim()
    if (value) benefits.append({ value })
    setBenefitDraft('')
  }

  return (
    <SettingsSection title="회사 소개" saving={save.isPending} onSave={() => void onSave()}>
      <SettingsRow label="회사 소개">
        <Textarea
          rows={2}
          placeholder="어떤 일을 하는 회사인지 적어 주세요."
          {...form.register('intro')}
        />
      </SettingsRow>
      <SettingsRow label="조직 문화">
        <Textarea
          rows={2}
          placeholder="일하는 방식과 문화를 적어 주세요."
          {...form.register('culture')}
        />
      </SettingsRow>
      <SettingsRow label="인재상">
        <div className="space-y-2">
          {talents.fields.map((field, index) => (
            <div
              key={field.id}
              className="group flex items-center gap-3 rounded-lg border px-3 py-1.5"
            >
              <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-semibold">
                {index + 1}
              </span>
              <input
                aria-label={`인재상 ${index + 1}`}
                placeholder="인재상"
                className="w-40 shrink-0 bg-transparent text-sm font-semibold outline-none"
                {...form.register(`talents.${index}.title`)}
              />
              <input
                aria-label={`인재상 ${index + 1} 설명`}
                placeholder="설명"
                className="min-w-0 flex-1 bg-transparent text-xs text-muted-foreground outline-none"
                {...form.register(`talents.${index}.description`)}
              />
              <button
                type="button"
                aria-label="인재상 삭제"
                className="invisible text-muted-foreground group-hover:visible hover:text-foreground"
                onClick={() => talents.remove(index)}
              >
                <X className="size-3.5" />
              </button>
            </div>
          ))}
          {talents.fields.length < 10 && (
            <AddButton onClick={() => talents.append({ title: '', description: '' })}>
              인재상 추가
            </AddButton>
          )}
        </div>
      </SettingsRow>
      <SettingsRow label="복지">
        <div className="flex flex-wrap items-center gap-2">
          {benefits.fields.map((field, index) => (
            <span
              key={field.id}
              className="group inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-sm"
            >
              {field.value}
              <button
                type="button"
                aria-label={`${field.value} 삭제`}
                className="hidden text-muted-foreground group-hover:inline hover:text-foreground"
                onClick={() => benefits.remove(index)}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
          <input
            value={benefitDraft}
            onChange={(event) => setBenefitDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
                event.preventDefault()
                addBenefit()
              }
            }}
            onBlur={addBenefit}
            placeholder="+ 복지 입력 후 Enter"
            aria-label="복지 추가"
            className="h-8 w-40 rounded-md px-2 text-sm outline-none placeholder:text-muted-foreground focus:bg-muted"
          />
        </div>
      </SettingsRow>
      <div className="border-t" />
      <SettingsRow label="참고 자료">
        <ReferenceFiles category="INTRO" />
      </SettingsRow>
    </SettingsSection>
  )
}

export function AddButton({ onClick, children }: { onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
    >
      <Plus className="size-3.5" />
      {children}
    </button>
  )
}
