import { Check, FileText, Image } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { Posting } from '@/features/posting/api'
import {
  companyPosterLogoUrl,
  savedPosterLogoUrl,
  usePosterBrand,
} from '@/features/posting/poster-api'
import { initialPoster, type PosterDesign } from '@/features/posting/poster-design'
import { PosterThumbnail } from '@/features/posting/PosterThumbnail'
import { useOrshotPoster } from '@/features/posting/useOrshotPoster'
import { cn } from '@/lib/utils'

export type PostingFormat = 'text' | 'poster'

export function PostingFormatDialog({
  posting,
  pending,
  onClose,
  onSelect,
}: {
  posting: Posting
  pending: boolean
  onClose: () => void
  onSelect: (format: PostingFormat, design: PosterDesign) => void
}) {
  const [selected, setSelected] = useState<PostingFormat | null>(null)
  const brand = usePosterBrand()
  const refreshed = useOrshotPoster(posting, {
    ...(posting.poster ?? initialPoster(brand.data)),
    enabled: true,
  })
  const design = refreshed.design
  const waitingForPoster = selected === 'poster' && (refreshed.isFetching || refreshed.isError)
  const logoUrl =
    design.logoFileId === brand.data?.logoFileId
      ? companyPosterLogoUrl(design.logoFileId)
      : savedPosterLogoUrl(posting.recruitmentId, design.logoFileId)
  const content = posting.content

  return (
    <Dialog open onOpenChange={(open) => !open && !pending && onClose()}>
      <DialogContent className="sm:max-w-[600px]" showCloseButton={!pending}>
        <DialogHeader>
          <DialogTitle>게시 형식을 선택해 주세요</DialogTitle>
          <DialogDescription>선택한 형식 하나만 채용 페이지에 표시돼요.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3" role="group" aria-label="게시 형식">
          {(['text', 'poster'] as const).map((format) => (
            <button
              key={format}
              type="button"
              aria-label={format === 'text' ? '글 공고 선택' : '포스터 공고 선택'}
              aria-pressed={selected === format}
              disabled={pending}
              onClick={() => setSelected(format)}
              className={cn(
                'relative min-w-0 rounded-xl border p-2 text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                selected === format
                  ? 'border-foreground ring-1 ring-foreground'
                  : 'hover:border-foreground/40',
              )}
            >
              <span
                className={cn(
                  'absolute top-4 right-4 z-10 flex size-5 items-center justify-center rounded-full border',
                  selected === format
                    ? 'border-foreground bg-foreground text-background'
                    : 'bg-background',
                )}
                aria-hidden="true"
              >
                {selected === format && <Check className="size-3" />}
              </span>
              <div className="overflow-hidden rounded-md border bg-surface" aria-hidden="true">
                {format === 'text' ? (
                  <div className="h-48 overflow-hidden p-3">
                    <div className="h-full overflow-hidden border bg-background p-3">
                      <p className="mb-2 text-[9px] text-muted-foreground">{posting.companyName}</p>
                      <p className="text-xs font-bold break-words">{content.title}</p>
                      <p className="mt-1 truncate text-[9px] text-muted-foreground">
                        {[content.jobCategory, content.career].filter(Boolean).join(' · ')}
                      </p>
                      {(
                        [
                          ['주요 업무', content.duties],
                          ['자격 요건', content.qualifications],
                        ] as const
                      ).map(([label, lines]) => (
                        <div key={label} className="mt-3 text-[9px]">
                          <p className="mb-1 font-semibold">{label}</p>
                          {lines.length ? (
                            lines.slice(0, 2).map((line) => (
                              <p key={line} className="truncate">
                                · {line}
                              </p>
                            ))
                          ) : (
                            <div className="h-1 w-4/5 rounded bg-muted" />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <PosterThumbnail posting={posting} design={design} logoUrl={logoUrl} />
                )}
              </div>
              <span className="mt-3 flex items-center gap-2 px-1 text-sm font-semibold">
                {format === 'text' ? <FileText className="size-4" /> : <Image className="size-4" />}
                {format === 'text' ? '글 공고' : '포스터 공고'}
              </span>
              <span className="mt-1 mb-1 block px-1 text-xs text-muted-foreground">
                {format === 'text'
                  ? '작성한 내용을 글로 게시해요.'
                  : '작성한 내용을 포스터로 게시해요.'}
              </span>
            </button>
          ))}
        </div>
        <p className="min-h-5 text-xs" aria-live="polite">
          {selected === 'text'
            ? '포스터 단계를 건너뛰고 최종 확인으로 이동해요.'
            : selected === 'poster'
              ? '포스터 템플릿 선택·편집으로 이동해요.'
              : '원하는 형식을 선택해 주세요.'}
        </p>
        {refreshed.isFetching && (
          <p role="status" className="text-xs text-muted-foreground">
            변경한 공고 제목을 포스터에 반영하고 있어요.
          </p>
        )}
        {refreshed.isError && (
          <div role="alert" className="text-xs">
            <p>포스터에 공고 변경 내용을 반영하지 못했어요.</p>
            <Button variant="outline" size="sm" onClick={() => void refreshed.refetch()}>
              다시 시도
            </Button>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={pending} onClick={onClose}>
            취소
          </Button>
          <Button
            disabled={!selected || pending || waitingForPoster}
            onClick={() => selected && onSelect(selected, design)}
          >
            {pending ? '저장 중…' : '선택'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
