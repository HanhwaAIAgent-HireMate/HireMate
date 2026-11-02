import { ArrowLeft, ArrowRight, FileDown, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { AiRequestPanel, type AiMessage } from '@/features/posting/AiRequestPanel'
import { usePosting, type Posting } from '@/features/posting/api'
import {
  companyPosterLogoUrl,
  savedPosterLogoUrl,
  usePosterAi,
  usePosterBrand,
  useSavePoster,
} from '@/features/posting/poster-api'
import {
  exportPosterPdf,
  initialPoster,
  POSTER_TEMPLATES,
  type PosterDesign,
  type PosterProposal,
} from '@/features/posting/poster-design'
import { PostingPoster } from '@/features/posting/PostingPoster'
import { PosterThumbnail } from '@/features/posting/PosterThumbnail'
import { PostingStepHeader } from '@/features/posting/PostingStepHeader'
import { usePostingRecovery } from '@/features/posting/usePostingRecovery'
import type { Schemas } from '@/lib/api/client'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

function sectionNames(element: HTMLElement | null) {
  return [...(element?.querySelectorAll('.poster-section-title h3') ?? [])].map(
    (heading) => heading.textContent?.trim() ?? '',
  )
}

export function PostingPosterPage() {
  const { recruitmentId = '' } = useParams()
  const posting = usePosting(recruitmentId)
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {posting.data ? (
        <PosterEditor key={posting.data.postingId} posting={posting.data} />
      ) : (
        <div className="p-6">
          <div className="mb-4 flex items-center gap-3">
            <h1 className="text-xl font-bold">공고 작성</h1>
            <span className="text-sm text-muted-foreground">Poster</span>
          </div>
          {posting.isError ? (
            <p role="alert">공고를 불러오지 못했어요.</p>
          ) : (
            <Skeleton className="h-80 w-full" />
          )}
        </div>
      )}
    </div>
  )
}

function PosterEditor({ posting }: { posting: Posting }) {
  const navigate = useNavigate()
  const brand = usePosterBrand()
  const save = useSavePoster(posting.recruitmentId)
  const ai = usePosterAi(posting.recruitmentId)
  const editable = posting.status === 'DRAFT'
  const recovery = usePostingRecovery(
    `${posting.recruitmentId}:poster`,
    posting.poster ?? initialPoster(),
    editable,
  )
  const { value: design, setValue: setDesign } = recovery
  const { value: history, setValue: setHistory } = usePostingRecovery<Schemas['PosterTurn'][]>(
    `${posting.recruitmentId}:poster-chat`,
    [],
    editable,
    false,
  )
  const [messages, setMessages] = useState<AiMessage[]>(() =>
    history.map((turn) => ({ role: turn.role === 'USER' ? 'user' : 'ai', text: turn.text })),
  )
  const [proposal, setProposal] = useState<PosterProposal | null>(null)
  const [preview, setPreview] = useState<PosterDesign | null>(null)
  const [exporting, setExporting] = useState(false)
  const [smallPane, setSmallPane] = useState<'options' | 'poster' | 'chat'>('poster')
  const poster = useRef<HTMLDivElement>(null)
  const recommended = useRef(false)
  const busy = save.isPending || ai.isPending
  const shown = preview ?? design
  const logoUrl =
    shown.logoFileId && shown.logoFileId === brand.data?.logoFileId
      ? companyPosterLogoUrl(shown.logoFileId)
      : savedPosterLogoUrl(posting.recruitmentId, shown.logoFileId)
  useEffect(() => {
    if (recommended.current || !editable || posting.poster?.enabled || history.length) return
    recommended.current = true
    ai.mutate(
      {
        message:
          '회사 소개와 문화, 공고 분량을 보고 어울리는 포스터 템플릿 2종과 분위기를 추천해줘. 브랜드 색상이 있으면 반영해줘.',
        design,
        history,
        sectionNames: sectionNames(poster.current),
      },
      {
        onSuccess: (result) => {
          setProposal(result)
          setHistory(
            (previous) =>
              [
                ...previous,
                {
                  role: 'ASSISTANT',
                  text: result.reply,
                  design: null,
                  recommendations: result.recommendations,
                },
              ].slice(-12) as Schemas['PosterTurn'][],
          )
          setMessages((current) => [
            ...current,
            { role: 'ai', text: result.reply, agent: 'Posting Agent' },
          ])
        },
        onError: (error) =>
          setMessages((current) => [...current, { role: 'ai', text: errorMessage(error) }]),
      },
    )
  }, [ai, design, editable, posting.poster?.enabled, history, setHistory])
  const update = (patch: Partial<PosterDesign>) => {
    setPreview(null)
    setProposal(null)
    setDesign((current) => ({ ...current, ...patch }))
  }
  const persist = async (next = design) => {
    try {
      const selected = { ...next, enabled: true }
      await save.mutateAsync(selected)
      setDesign(selected)
      return true
    } catch (error) {
      toast.error(errorMessage(error))
      return false
    }
  }
  const request = async (message: string) => {
    setMessages((current) => [...current, { role: 'user', text: message }])
    try {
      const result = await ai.mutateAsync({
        message,
        design,
        history,
        sectionNames: sectionNames(poster.current),
      })
      setHistory(
        (previous) =>
          [
            ...previous,
            { role: 'USER', text: message, design, recommendations: [] },
            {
              role: 'ASSISTANT',
              text: result.reply,
              design: null,
              recommendations: result.recommendations,
            },
          ].slice(-12) as Schemas['PosterTurn'][],
      )
      setProposal(result)
      setPreview(null)
      setMessages((current) => [
        ...current,
        { role: 'ai', text: result.reply, agent: 'Posting Agent' },
      ])
    } catch (error) {
      setMessages((current) => [...current, { role: 'ai', text: errorMessage(error) }])
    }
  }
  const pdf = async () => {
    const element = poster.current?.firstElementChild
    if (!(element instanceof HTMLElement)) return
    setExporting(true)
    try {
      await exportPosterPdf(element, posting.content.title)
      toast.info('인쇄 대상에서 ‘PDF로 저장’을 선택해 주세요.')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setExporting(false)
    }
  }

  const chatPanel = (
    <AiRequestPanel
      messages={messages}
      examples={[
        '우리는 더 고급스러운 느낌이 있어야 해',
        '더 청량하게, 물결 장식은 은은하게 해줘',
        '회사 소개에 어울리는 디자인을 추천해줘',
        '실무면접 아이콘을 사람 아이콘으로 바꿔줘',
      ]}
      hint="분위기와 장식은 이곳에서 요청해 주세요. AI 수정안은 적용해야 반영돼요."
      pending={ai.isPending}
      disabled={busy}
      onSend={(message) => void request(message)}
      onReset={() => {
        if (busy) return
        recommended.current = true
        setMessages([])
        setHistory([])
      }}
    />
  )
  return (
    <>
      <PostingStepHeader title="공고 작성" caption="Poster">
        <Button
          variant="outline"
          className="min-w-20"
          disabled={busy}
          onClick={() => {
            const back = () =>
              void navigate('/hr/recruitments/' + posting.recruitmentId + '/posting')
            if (!editable) {
              back()
              return
            }
            void persist().then((ok) => {
              if (ok) back()
            })
          }}
        >
          <ArrowLeft />
          이전
        </Button>
        {!editable && (
          <Button
            variant="outline"
            onClick={() => void pdf()}
            disabled={!shown.enabled || exporting}
          >
            <FileDown />
            PDF 내보내기
          </Button>
        )}
        {editable && (
          <Button
            variant="outline"
            className="min-w-20"
            disabled={busy || !!preview}
            onClick={() =>
              void persist().then((ok) => {
                if (ok) toast.success('포스터를 임시 저장했어요.')
              })
            }
          >
            임시 저장
          </Button>
        )}
        {editable && (
          <Button
            className="min-w-20"
            onClick={() => {
              if (preview) {
                toast.info('AI 수정안을 적용하거나 되돌린 뒤 진행해 주세요.')
                return
              }
              void persist().then((ok) => {
                if (ok)
                  void navigate('/hr/recruitments/' + posting.recruitmentId + '/posting/publish')
              })
            }}
            disabled={busy}
          >
            다음
            <ArrowRight />
          </Button>
        )}
      </PostingStepHeader>
      {editable && recovery.dirty && (
        <p role="status" className="border-b bg-muted px-6 py-2 text-xs text-muted-foreground">
          {recovery.restored ? '저장하지 않은 디자인을 복구했어요. ' : ''}
          변경 내용은 이 탭에 임시 보관돼요. 공고에 반영하려면 임시 저장을 눌러 주세요.
        </p>
      )}
      <nav
        className="flex shrink-0 gap-1 border-b px-4 py-2 lg:hidden"
        aria-label="포스터 편집 영역"
      >
        {(
          [
            { id: 'options', label: '디자인 옵션' },
            { id: 'poster', label: '포스터' },
            { id: 'chat', label: 'AI 수정 요청' },
          ] as const
        )
          .filter((item) => editable || item.id !== 'chat')
          .map((item) => (
            <Button
              key={item.id}
              variant={smallPane === item.id ? 'secondary' : 'ghost'}
              size="sm"
              aria-pressed={smallPane === item.id}
              onClick={() => setSmallPane(item.id)}
            >
              {item.label}
            </Button>
          ))}
      </nav>
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside
          aria-label="디자인 옵션"
          className={cn(
            'min-h-0 w-full shrink-0 flex-col border-r bg-background lg:flex lg:w-[272px] xl:w-[296px]',
            smallPane === 'options' ? 'flex' : 'hidden',
          )}
        >
          <div className="flex h-12 shrink-0 items-center justify-between border-b px-4">
            <h2 className="text-sm font-semibold">디자인 옵션</h2>
            {editable && (
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() =>
                  void request('회사 소개와 문화, 공고 분량에 맞는 포스터 템플릿 2종을 추천해줘.')
                }
              >
                <Sparkles />
                AI 추천
              </Button>
            )}
          </div>
          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-4">
            {!editable && (
              <p className="text-xs leading-5 text-muted-foreground">
                게시한 포스터는 수정할 수 없어요.
              </p>
            )}
            {proposal && proposal.recommendations.length > 0 && (
              <section className="rounded-lg bg-pass p-3">
                <h2 className="text-xs font-semibold">AI 디자인 제안 · 적용 전</h2>
                <div className="mt-3 space-y-3">
                  {proposal.recommendations.map((item, index) => (
                    <div key={index} className="rounded-md border bg-background p-3">
                      <strong className="text-xs">
                        {
                          POSTER_TEMPLATES.find((template) => template.id === item.design.template)
                            ?.name
                        }
                      </strong>
                      <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                        {item.reason}
                      </p>
                      <div className="mt-2 flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setPreview(item.design)
                            setSmallPane('poster')
                          }}
                          disabled={busy}
                        >
                          미리보기
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => {
                            setDesign(item.design)
                            setPreview(null)
                            setProposal(null)
                            setSmallPane('poster')
                            toast.success('편집 화면에 적용했어요. 저장하면 공고에 반영돼요.')
                          }}
                          disabled={busy}
                        >
                          수정안 적용
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  onClick={() => {
                    setProposal(null)
                    setPreview(null)
                  }}
                >
                  제안 되돌리기
                </Button>
              </section>
            )}
            <section aria-label="템플릿 선택">
              <h3 className="mb-3 text-xs font-medium">템플릿 선택</h3>
              <div className="grid grid-cols-2 gap-2">
                {POSTER_TEMPLATES.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    disabled={!editable || busy}
                    aria-pressed={design.template === item.id}
                    onClick={() => update({ template: item.id, enabled: true })}
                    className={cn(
                      'overflow-hidden rounded-md border text-left disabled:cursor-default',
                      design.template === item.id
                        ? 'border-foreground ring-1 ring-foreground'
                        : 'hover:border-foreground/40',
                    )}
                  >
                    <PosterThumbnail
                      posting={posting}
                      design={{ ...design, template: item.id, enabled: true }}
                      logoUrl={logoUrl}
                      compact
                    />
                    <div className="border-t bg-background px-2 py-2">
                      <strong className="block text-[11px]">{item.name}</strong>
                      <span className="sr-only">{item.description}</span>
                    </div>
                  </button>
                ))}
              </div>
            </section>
            {(brand.data?.templates ?? []).length > 0 && (
              <section aria-label="회사 전용 템플릿">
                <h3 className="mb-3 text-xs font-medium">회사 전용 템플릿</h3>
                <div className="space-y-2">
                  {brand.data?.templates.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      disabled={!editable || busy}
                      className="flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left hover:bg-muted disabled:cursor-default"
                      onClick={() => {
                        const base = POSTER_TEMPLATES.find((base) => base.id === item.template)
                        if (!base) return
                        update({
                          template: base.id,
                          color: item.color,
                          mood: base.mood,
                          decoration: item.decoration,
                          enabled: true,
                        })
                      }}
                    >
                      <span
                        className="size-5 shrink-0 rounded border"
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="min-w-0">
                        <strong className="block truncate text-xs">{item.name}</strong>
                        <span className="text-[11px] text-muted-foreground">
                          {POSTER_TEMPLATES.find((base) => base.id === item.template)?.name}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            )}
            <fieldset disabled={!editable || busy} className="space-y-5 border-t pt-5">
              <div>
                <label htmlFor="poster-color" className="mb-2 block text-xs font-medium">
                  대표 색상
                </label>
                <div className="flex items-center gap-3">
                  <input
                    id="poster-color"
                    type="color"
                    value={design.color}
                    onChange={(event) => update({ color: event.target.value })}
                    className="h-9 w-12 rounded border p-1"
                  />
                  <span className="font-mono text-xs">{design.color}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!brand.data}
                    onClick={() => update({ color: brand.data?.color ?? design.color })}
                  >
                    기업 색상
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      update({
                        color:
                          POSTER_TEMPLATES.find((item) => item.id === design.template)?.color ??
                          '#2459a6',
                      })
                    }
                  >
                    템플릿 색상
                  </Button>
                </div>
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={design.showLogo}
                    disabled={!design.logoFileId}
                    onChange={(event) => update({ showLogo: event.target.checked })}
                  />
                  회사 로고 표시
                </label>
                <Link
                  to="/hr/settings/posting"
                  className="mt-2 inline-block text-xs text-muted-foreground underline"
                >
                  로고 · 회사 템플릿 관리
                </Link>
              </div>
              <Button
                variant="outline"
                className="w-full"
                disabled={!brand.data}
                onClick={() => {
                  update({ ...initialPoster(brand.data), enabled: design.enabled })
                  toast.info('최신 기업 기본값을 가져왔어요.')
                }}
              >
                최신 기업 설정 가져오기
              </Button>
            </fieldset>
          </div>
        </aside>
        <section
          aria-label="포스터 미리보기"
          className={cn(
            'min-h-0 min-w-0 flex-1 flex-col bg-surface/60 lg:flex',
            smallPane === 'poster' ? 'flex' : 'hidden',
          )}
        >
          <div className="flex h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b px-5 text-xs text-muted-foreground">
            <span>{preview ? 'AI 수정안 미리보기' : '포스터 미리보기'}</span>
            <span>
              {preview ? '적용 전' : shown.enabled ? '공고 내용과 연결됨' : '포스터 사용 안 함'}
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 lg:px-6" data-poster-canvas>
            <div ref={poster} className="mx-auto max-w-[780px]">
              <PostingPoster
                posting={posting}
                design={shown}
                logoUrl={logoUrl}
                careersUrl={
                  !editable
                    ? new URL(`/careers/${posting.postingId}`, window.location.origin).href
                    : undefined
                }
              />
            </div>
          </div>
        </section>
        {editable && (
          <div
            aria-label="포스터 AI 챗"
            className={cn(
              'min-h-0 w-full shrink-0 lg:flex lg:w-[300px]',
              smallPane === 'chat' ? 'flex' : 'hidden',
            )}
          >
            <div className="flex min-h-0 w-full [&>aside]:w-full">{chatPanel}</div>
          </div>
        )}
      </div>
    </>
  )
}
