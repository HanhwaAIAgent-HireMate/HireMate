import { zodResolver } from '@hookform/resolvers/zod'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useCompanyProfile } from '@/features/company/api'
import { companyPosterLogoUrl, useAddPosterTemplate } from '@/features/posting/poster-api'
import { initialPoster, POSTER_TEMPLATES, type PosterBrand } from '@/features/posting/poster-design'
import { PosterThumbnail } from '@/features/posting/PosterThumbnail'
import type { PosterPosting } from '@/features/posting/PostingPoster'
import { errorMessage } from '@/lib/api/client'

const schema = z.object({
  name: z.string().trim().min(1, '템플릿 이름을 입력해 주세요.').max(60),
  template: z.enum(['CLASSIC', 'EDITORIAL', 'BOLD', 'PREMIUM', 'NATURAL', 'TICKET']),
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/),
})
type Values = z.infer<typeof schema>

export function PosterTemplateDialog({ brand }: { brand: PosterBrand }) {
  const [open, setOpen] = useState(false)
  const company = useCompanyProfile()
  const add = useAddPosterTemplate()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', template: initialPoster(brand).template, color: brand.color },
  })
  const template = useWatch({ control: form.control, name: 'template' })
  const color = useWatch({ control: form.control, name: 'color' })
  const preview: PosterPosting = {
    companyName: company.data?.name ?? '회사명',
    openAt: null,
    closeAt: null,
    stages: [],
    documents: [],
    notices: [],
    content: {
      roles: [],
      title: '채용 공고',
      jobCategory: '',
      employmentType: '',
      career: '',
      location: '',
      intro: company.data?.intro ?? '',
      duties: [],
      qualifications: [],
      preferred: [],
      benefits: company.data?.benefits ?? [],
      headcount: null,
      position: '',
      education: '',
      workHours: '',
      salary: '',
    },
  }
  const submit = form.handleSubmit((body) =>
    add.mutate(body, {
      onSuccess: () => {
        setOpen(false)
        form.reset({ ...body, name: '' })
        toast.success('회사 전용 템플릿을 추가했어요. 공고에서 선택할 수 있어요.')
      },
      onError: (error) => toast.error(errorMessage(error)),
    }),
  )
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label="새 템플릿 추가"
          disabled={brand.templates.length >= 12}
          className="flex h-60 w-44 shrink-0 snap-start items-center justify-center rounded-lg border border-dashed text-muted-foreground transition-colors hover:border-foreground/40 hover:bg-muted/50 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="size-8" aria-hidden="true" />
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>새 포스터 템플릿</DialogTitle>
          <DialogDescription>
            기본 레이아웃에 이름과 회사 색상을 더해 저장해요. 실제 문구는 각 공고에서 채워져요.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="space-y-4">
          <div>
            <label htmlFor="new-poster-template-name" className="mb-1.5 block text-xs font-medium">
              템플릿 이름
            </label>
            <Input
              id="new-poster-template-name"
              placeholder="예: 우리 회사 기본 채용"
              maxLength={60}
              {...form.register('name')}
            />
            {form.formState.errors.name && (
              <p role="alert" className="mt-1 text-xs text-destructive">
                {form.formState.errors.name.message}
              </p>
            )}
          </div>
          <div>
            <label
              htmlFor="new-poster-template-layout"
              className="mb-1.5 block text-xs font-medium"
            >
              기본 레이아웃
            </label>
            <select
              id="new-poster-template-layout"
              className="h-9 w-full rounded-md border bg-background px-2 text-sm"
              {...form.register('template')}
            >
              {POSTER_TEMPLATES.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center justify-between">
            <label htmlFor="new-poster-template-color" className="text-xs font-medium">
              대표 색상
            </label>
            <input
              id="new-poster-template-color"
              type="color"
              className="h-9 w-14 rounded border p-1"
              {...form.register('color')}
            />
          </div>
          <div className="overflow-hidden rounded-md border">
            <PosterThumbnail
              posting={preview}
              design={{
                ...initialPoster(brand),
                template,
                mood: POSTER_TEMPLATES.find((item) => item.id === template)?.mood ?? 'TRUST',
                color,
                enabled: true,
              }}
              logoUrl={companyPosterLogoUrl(brand.logoFileId)}
            />
          </div>
          <Button type="submit" className="w-full" disabled={add.isPending}>
            {add.isPending ? '추가 중…' : '템플릿 추가'}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
