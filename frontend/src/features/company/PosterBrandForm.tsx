import { zodResolver } from '@hookform/resolvers/zod'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { useCompanyProfile } from '@/features/company/api'
import { SettingsRow, SettingsSection } from '@/features/company/SettingsSection'
import { PosterTemplateDialog } from '@/features/company/PosterTemplateDialog'
import {
  companyPosterLogoUrl,
  usePosterBrand,
  useSavePosterBrand,
} from '@/features/posting/poster-api'
import { initialPoster, POSTER_TEMPLATES } from '@/features/posting/poster-design'
import { PosterThumbnail } from '@/features/posting/PosterThumbnail'
import type { PosterPosting } from '@/features/posting/PostingPoster'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const schema = z.object({
  template: z.enum(['CLASSIC', 'EDITORIAL', 'BOLD', 'PREMIUM', 'NATURAL', 'TICKET']),
  mood: z.enum(['TRUST', 'CLEAR', 'WARM', 'PREMIUM', 'LIVELY', 'NATURAL']),
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/, '6자리 색상 코드를 입력해 주세요.'),
  decoration: z.number().int().min(0).max(2),
})
type Values = z.infer<typeof schema>

export function PosterBrandForm() {
  const templateList = useRef<HTMLDivElement>(null)
  const brand = usePosterBrand()
  const company = useCompanyProfile()
  const save = useSavePosterBrand()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { template: 'CLASSIC', mood: 'TRUST', color: '#2459a6', decoration: 1 },
  })
  const [template, color, mood, decoration] = useWatch({
    control: form.control,
    name: ['template', 'color', 'mood', 'decoration'],
  })
  const design = { ...initialPoster(brand.data), template, color, mood, decoration, enabled: true }
  const selectedCompanyTemplate = brand.data?.templates.find(
    (item) => item.template === template && item.color === color && item.decoration === decoration,
  )
  const preview: PosterPosting = {
    companyName: company.data?.name ?? '회사명',
    openAt: null,
    closeAt: null,
    stages: [],
    documents: [],
    notices: [],
    content: {
      roles: [],
      blind: false,
      title: '함께할 동료를 찾습니다',
      jobCategory: '모집 직무',
      employmentType: '',
      career: '',
      location: '',
      intro: company.data?.intro ?? '',
      duties: ['담당할 주요 업무를 안내해요.'],
      qualifications: ['직무에 필요한 역량과 경험을 소개해요.'],
      preferred: [],
      benefits: company.data?.benefits ?? ['함께 일하는 환경을 소개해요.'],
      headcount: null,
      position: '',
      education: '',
      workHours: '',
      salary: '',
    },
  }
  useEffect(() => {
    const parsed = schema.safeParse(brand.data)
    if (parsed.success) form.reset(parsed.data)
  }, [brand.data, form])
  const onSave = form.handleSubmit((body) =>
    save.mutate(body, {
      onSuccess: () => toast.success('새 공고의 포스터 기본값을 저장했어요.'),
      onError: (error) => toast.error(errorMessage(error)),
    }),
  )
  return (
    <SettingsSection
      title="포스터 템플릿"
      saving={save.isPending || !brand.data}
      onSave={() => void onSave()}
    >
      <p className="text-sm text-muted-foreground">
        새 공고의 기본 디자인이에요. 기존 공고와 게시된 포스터에는 영향을 주지 않아요.
      </p>
      {brand.isError && (
        <p role="alert" className="text-sm text-destructive">
          포스터 설정을 불러오지 못했어요.
        </p>
      )}
      <fieldset disabled={!brand.data || save.isPending} className="space-y-5">
        <SettingsRow label="기본 템플릿">
          <div className="space-y-3">
            <div className="flex justify-end gap-1">
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                aria-label="이전 템플릿 보기"
                onClick={() => templateList.current?.scrollBy({ left: -188, behavior: 'smooth' })}
              >
                <ChevronLeft />
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                aria-label="다음 템플릿 보기"
                onClick={() => templateList.current?.scrollBy({ left: 188, behavior: 'smooth' })}
              >
                <ChevronRight />
              </Button>
            </div>
            <div
              ref={templateList}
              role="region"
              aria-label="포스터 템플릿 미리보기"
              tabIndex={0}
              className="flex snap-x snap-mandatory items-start gap-3 overflow-x-auto px-1 pt-1 pb-3 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {brand.data && <PosterTemplateDialog brand={brand.data} />}
              {POSTER_TEMPLATES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={template === item.id && !selectedCompanyTemplate}
                  onClick={() => form.setValue('template', item.id, { shouldDirty: true })}
                  className={cn(
                    'flex h-60 w-44 shrink-0 snap-start flex-col overflow-hidden rounded-lg border text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none',
                    template === item.id && !selectedCompanyTemplate
                      ? 'border-foreground ring-1 ring-foreground'
                      : 'hover:border-foreground/40',
                  )}
                >
                  <PosterThumbnail
                    posting={preview}
                    design={{ ...design, template: item.id }}
                    logoUrl={companyPosterLogoUrl(brand.data?.logoFileId)}
                    fill
                  />
                  <div className="flex min-h-0 w-full flex-1 items-center justify-center border-t bg-background px-3 text-center">
                    <strong className="block text-sm">{item.name}</strong>
                  </div>
                </button>
              ))}
              {(brand.data?.templates ?? []).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={selectedCompanyTemplate?.id === item.id}
                  onClick={() => {
                    const base = POSTER_TEMPLATES.find((base) => base.id === item.template)
                    if (!base) return
                    form.setValue('template', base.id, { shouldDirty: true })
                    form.setValue('color', item.color, { shouldDirty: true })
                    form.setValue('mood', base.mood, { shouldDirty: true })
                    form.setValue('decoration', item.decoration, { shouldDirty: true })
                  }}
                  className={cn(
                    'flex h-60 w-44 shrink-0 snap-start flex-col overflow-hidden rounded-lg border text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none',
                    selectedCompanyTemplate?.id === item.id
                      ? 'border-foreground ring-1 ring-foreground'
                      : 'hover:border-foreground/40',
                  )}
                >
                  <PosterThumbnail
                    posting={preview}
                    design={{
                      ...design,
                      template:
                        POSTER_TEMPLATES.find((base) => base.id === item.template)?.id ?? 'CLASSIC',
                      color: item.color,
                      decoration: item.decoration,
                    }}
                    logoUrl={companyPosterLogoUrl(brand.data?.logoFileId)}
                    fill
                  />
                  <div className="flex min-h-0 w-full flex-1 items-center justify-center border-t bg-background px-3 text-center">
                    <strong className="block truncate text-sm">{item.name}</strong>
                  </div>
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              회사 전용 템플릿은 최대 12개까지 저장할 수 있어요.
            </p>
          </div>
        </SettingsRow>
        <SettingsRow label="브랜드 색상">
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="color"
              aria-label="기본 포스터 색상"
              className="h-10 w-14 rounded border p-1"
              {...form.register('color')}
            />
            <span className="text-xs text-muted-foreground">
              포스터에 사용할 대표 색상을 바꿀 수 있어요.
            </span>
          </div>
          {form.formState.errors.color && <p role="alert">{form.formState.errors.color.message}</p>}
        </SettingsRow>
      </fieldset>
    </SettingsSection>
  )
}
