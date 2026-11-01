import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { SettingsRow, SettingsSection } from '@/features/company/SettingsSection'
import { PosterTemplateDialog } from '@/features/company/PosterTemplateDialog'
import {
  companyPosterLogoUrl,
  usePosterBrand,
  useSavePosterBrand,
} from '@/features/posting/poster-api'
import { POSTER_TEMPLATES } from '@/features/posting/poster-design'
import { errorMessage } from '@/lib/api/client'

const schema = z.object({
  template: z.enum(['CLASSIC', 'EDITORIAL', 'BOLD', 'PREMIUM', 'NATURAL', 'TICKET']),
  mood: z.enum(['TRUST', 'CLEAR', 'WARM', 'PREMIUM', 'LIVELY', 'NATURAL']),
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/, '6자리 색상 코드를 입력해 주세요.'),
  decoration: z.number().int().min(0).max(2),
})
type Values = z.infer<typeof schema>

export function PosterBrandForm() {
  const brand = usePosterBrand()
  const save = useSavePosterBrand()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { template: 'CLASSIC', mood: 'TRUST', color: '#2459a6', decoration: 1 },
  })
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
        {/* 로고는 설정 › 회사 소개에서 올려 안내 메일과 같이 쓴다. 여기서는 보여 주기만 한다 */}
        <SettingsRow label="회사 로고">
          <div className="space-y-2">
            {brand.data?.logoFileId && (
              <img
                src={companyPosterLogoUrl(brand.data.logoFileId)}
                alt="포스터용 회사 로고"
                className="h-14 max-w-40 rounded border bg-white object-contain p-2"
              />
            )}
            <p className="text-xs text-muted-foreground">
              로고는{' '}
              <Link to="/hr/settings" className="underline">
                설정 › 회사 소개
              </Link>
              에서 올리고 바꿔요. 올리면 포스터 대표 색상도 로고에 맞춰요.
            </p>
          </div>
        </SettingsRow>
        <SettingsRow label="기본 템플릿">
          <select
            aria-label="기본 포스터 템플릿"
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
            {...form.register('template')}
          >
            {POSTER_TEMPLATES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} — {item.description}
              </option>
            ))}
          </select>
        </SettingsRow>
        <SettingsRow label="회사 템플릿">
          <div className="space-y-3">
            {brand.data && <PosterTemplateDialog brand={brand.data} />}
            {(brand.data?.templates ?? []).map((item) => (
              <div key={item.id} className="flex items-center gap-3 rounded-md border px-3 py-2">
                <span
                  className="size-5 shrink-0 rounded border"
                  style={{ backgroundColor: item.color }}
                />
                <div className="min-w-0 flex-1">
                  <strong className="block truncate text-sm">{item.name}</strong>
                  <span className="text-xs text-muted-foreground">
                    {POSTER_TEMPLATES.find((base) => base.id === item.template)?.name}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const base = POSTER_TEMPLATES.find((base) => base.id === item.template)
                    if (!base) return
                    form.setValue('template', base.id)
                    form.setValue('color', item.color)
                    form.setValue('mood', base.mood)
                    form.setValue('decoration', item.decoration)
                    toast.info('기본값에 불러왔어요. 저장을 눌러 반영해 주세요.')
                  }}
                >
                  기본값에 적용
                </Button>
              </div>
            ))}
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
              로고를 올리면 대표 색상을 추출해요. 원하는 색으로 바꿀 수 있어요.
            </span>
          </div>
          {form.formState.errors.color && <p role="alert">{form.formState.errors.color.message}</p>}
        </SettingsRow>
      </fieldset>
      <p className="text-xs text-muted-foreground">
        회사 소개 기반 AI 추천은 개별 공고의 포스터 디자인 단계에서 확인해요.{' '}
        <Link to="/hr/settings" className="underline">
          회사 소개 수정
        </Link>
      </p>
    </SettingsSection>
  )
}
