import { ArrowLeft, ArrowRight, FileDown, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PosterTemplateDelete } from '@/features/company/PosterTemplateDelete'
import { AiRequestPanel, type AiMessage } from '@/features/posting/AiRequestPanel'
import { usePosting, type Posting } from '@/features/posting/api'
import {
  companyPosterLogoUrl,
  useAddPosterTemplate,
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
import { useSaveDraftOnLeave } from '@/features/posting/useSaveDraftOnLeave'
import { posterPreviewChanges } from '@/features/posting/poster-preview'
import {
  importPosterTemplate,
  importCanvaPoster,
  readPosterCanvas,
  samePosterCanvas,
  posterAfterTemplateDeletion,
  nextExternalTemplateName,
  upgradeCanvaPoster,
  type FreeTemplate,
} from '@/features/posting/poster-canvas'
import type { Schemas } from '@/lib/api/client'
import { api, unwrap, errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'
import { nativeRegions, importNativePoster } from '@/features/posting/poster-layout'

function sectionNames(element: HTMLElement | null) {
  return [...(element?.querySelectorAll('.poster-section-title h3') ?? [])].map(
    (heading) => heading.textContent?.trim() ?? '',
  )
}

function proposalName(design: PosterDesign) {
  if (design.canvasJson) {
    try {
      return readPosterCanvas(design.canvasJson).source.name
    } catch {
      return '외부 템플릿'
    }
  }
  return POSTER_TEMPLATES.find((template) => template.id === design.template)?.name
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
            <h1 className="text-xl font-bold">공고 디자인</h1>
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
  const addTemplate = useAddPosterTemplate()
  const save = useSavePoster(posting.recruitmentId)
  const ai = usePosterAi(posting.recruitmentId)
  const editable = posting.status === 'DRAFT'
  const recovery = usePostingRecovery(
    `${posting.recruitmentId}:poster`,
    posting.poster ?? initialPoster(),
    editable,
  )
  const { value: design, setValue: setDesign } = recovery
  const savedDesign = JSON.stringify(posting.poster ?? initialPoster())
  const savedDesignRef = useRef(savedDesign)
  useEffect(() => {
    savedDesignRef.current = savedDesign
  }, [savedDesign])
  const restoredNotice = useRef(false)
  useEffect(() => {
    if (!recovery.restored || !recovery.dirty || restoredNotice.current) return
    restoredNotice.current = true
    toast.info('저장하지 않은 포스터 디자인을 복구했어요.')
  }, [recovery.restored, recovery.dirty])
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
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [smallPane, setSmallPane] = useState<'options' | 'poster' | 'chat'>('poster')
  const poster = useRef<HTMLDivElement>(null)
  const recommended = useRef(false)
  const busy = save.isPending || ai.isPending || addTemplate.isPending || importing
  const shown = preview ?? design
  const changes = useMemo(
    () => (preview ? posterPreviewChanges(design, preview, posting) : undefined),
    [design, preview, posting],
  )
  useEffect(() => {
    const root = poster.current
    if (!preview || !root) return
    const focus = () => {
      const changed = root.querySelector<HTMLElement>('[data-poster-highlight]')
      if (!changed) return false
      changed.scrollIntoView({ block: 'center', behavior: 'smooth' })
      return true
    }
    if (focus()) return
    const observer = new MutationObserver(() => {
      if (focus()) observer.disconnect()
    })
    observer.observe(root, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [preview, changes])
  const logoUrl =
    shown.logoFileId && shown.logoFileId === brand.data?.logoFileId
      ? companyPosterLogoUrl(shown.logoFileId)
      : savedPosterLogoUrl(posting.recruitmentId, shown.logoFileId)
  useEffect(() => {
    const original = design.canvasJson
    if (!editable || !original) return
    let active = true
    void upgradeCanvaPoster(original, posting, design.color)
      .then((upgraded) => {
        if (active && upgraded !== original)
          setDesign((current) =>
            current.canvasJson === original ? { ...current, canvasJson: upgraded } : current,
          )
      })
      .catch(() => {
        if (active)
          toast.error('기존 Canva 양식을 다시 구성하지 못했어요. 원본을 다시 가져와 주세요.')
      })
    return () => {
      active = false
    }
  }, [design.canvasJson, design.color, editable, posting, setDesign])
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
          setPreview(result.recommendations[0]?.design ?? null)
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
  const persist = async (next = design, notify = false) => {
    try {
      const selected = { ...next, enabled: true }
      await save.mutateAsync(selected)
      savedDesignRef.current = JSON.stringify(selected)
      setDesign(selected)
      if (notify) toast.success('임시 저장했어요.')
      return true
    } catch (error) {
      toast.error(errorMessage(error))
      return false
    }
  }
  useSaveDraftOnLeave({
    enabled: editable,
    isDirty: () => JSON.stringify(design) !== savedDesignRef.current,
    save: () => persist(),
  })
  const request = async (message: string) => {
    const current = preview ?? design
    setMessages((current) => [...current, { role: 'user', text: message }])
    try {
      const result = await ai.mutateAsync({
        message,
        design: current,
        history,
        sectionNames: sectionNames(poster.current),
      })
      const names = [
        ...(brand.data?.templates?.map((item) => item.name) ?? []),
        ...history.flatMap((turn) =>
          turn.recommendations.map((item) => proposalName(item.design) ?? ''),
        ),
      ]
      const knownNames = new Map<string, string>()
      for (const saved of [
        ...(brand.data?.templates?.map((item) => item.canvasJson) ?? []),
        ...history.flatMap((turn) => turn.recommendations.map((item) => item.design.canvasJson)),
        design.canvasJson,
      ]) {
        if (!saved) continue
        try {
          const source = readPosterCanvas(saved).source
          if (source.id) knownNames.set(source.id, source.name)
        } catch {
          continue
        }
      }
      result.recommendations = result.recommendations.map((item) => {
        if (!item.design.canvasJson) return item
        const canvas = readPosterCanvas(item.design.canvasJson)
        if (canvas.source.url !== 'hiremate:generated') return item
        const name =
          (canvas.source.id && knownNames.get(canvas.source.id)) ||
          nextExternalTemplateName(names, '생성템플릿')
        names.push(name)
        canvas.source.name = name
        return { ...item, design: { ...item.design, canvasJson: JSON.stringify(canvas) } }
      })
      setHistory(
        (previous) =>
          [
            ...previous,
            { role: 'USER', text: message, design: current, recommendations: [] },
            {
              role: 'ASSISTANT',
              text: result.reply,
              design: null,
              recommendations: result.recommendations,
              templates: result.templates ?? [],
            },
          ].slice(-12) as Schemas['PosterTurn'][],
      )
      setProposal(result)
      setPreview(result.recommendations[0]?.design ?? null)
      if (result.recommendations.length) setSmallPane('poster')
      setMessages((current) => [
        ...current,
        { role: 'ai', text: result.reply, agent: 'Posting Agent' },
      ])
      const selected = result.templates?.find((item) => item.id === result.selectedTemplateId)
      if (selected) await importTemplate(selected)
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

  const importTemplate = async (template: FreeTemplate) => {
    setImporting(true)
    try {
      let canvasJson: string
      if (template.id.startsWith('templated:') && nativeRegions(template.svg).length > 1) {
        const plan = await unwrap(
          api.POST('/api/recruitments/{recruitmentId}/posting/poster/template-layout', {
            params: { path: { recruitmentId: posting.recruitmentId } },
            body: { regions: nativeRegions(template.svg) },
          }),
        )
        canvasJson = await importNativePoster(template, plan, design.color)
      } else {
        canvasJson = await importPosterTemplate(template, posting, design.color)
      }
      const source = readPosterCanvas(canvasJson).source
      const existing = brand.data?.templates.find((item) => {
        if (!item.canvasJson) return false
        try {
          const saved = readPosterCanvas(item.canvasJson).source
          return saved.id ? saved.id === source.id : saved.name === source.name
        } catch {
          return false
        }
      })
      const name =
        existing?.name ??
        nextExternalTemplateName(brand.data?.templates.map((item) => item.name) ?? [])
      const document = readPosterCanvas(canvasJson)
      document.source.name = name
      canvasJson = JSON.stringify(document)
      if (!existing) {
        await addTemplate.mutateAsync({
          name,
          template: 'CLASSIC',
          color: design.color,
          canvasJson,
        })
      }
      setDesign((current) => ({ ...current, enabled: true, canvasJson }))
      setPreview(null)
      setProposal(null)
      setSmallPane('poster')
      toast.success('템플릿 선택에 추가하고 공고에 적용했어요.')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setImporting(false)
    }
  }

  const applyRecommendation = async (next: PosterDesign) => {
    try {
      if (next.canvasJson) {
        const canvas = readPosterCanvas(next.canvasJson)
        if (
          canvas.source.url === 'hiremate:generated' &&
          !brand.data?.templates.some((item) => samePosterCanvas(item.canvasJson, next.canvasJson))
        ) {
          await addTemplate.mutateAsync({
            name: canvas.source.name,
            template: next.template,
            color: next.color,
            canvasJson: next.canvasJson,
          })
        }
      }
      setDesign(next)
      setPreview(null)
      setProposal(null)
      setSmallPane('poster')
      toast.success('편집 화면에 적용했어요. 저장하면 공고에 반영돼요.')
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const importCanva = async (designId: string) => {
    setImportError(null)
    setImporting(true)
    try {
      const imported = await unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/poster/canva-import', {
          params: { path: { recruitmentId: posting.recruitmentId } },
          body: { designId },
        }),
      )
      const canvasJson = await importCanvaPoster(imported, posting, design.color)
      const name = nextExternalTemplateName(brand.data?.templates.map((item) => item.name) ?? [])
      const document = readPosterCanvas(canvasJson)
      document.source.name = name
      const namedCanvas = JSON.stringify(document)
      await addTemplate.mutateAsync({
        name,
        template: 'CLASSIC',
        color: design.color,
        canvasJson: namedCanvas,
      })
      update({ canvasJson: namedCanvas, enabled: true })
      setSmallPane('poster')
      toast.success('Canva 디자인을 템플릿에 추가하고 현재 공고를 채웠어요.')
    } catch (error) {
      setImportError(errorMessage(error))
      toast.error(errorMessage(error))
    } finally {
      setImporting(false)
    }
  }

  const chatPanel = (
    <AiRequestPanel
      messages={messages}
      examples={[
        '새로운 포스터 템플릿 2개 만들어줘',
        '금융권에 어울리는 외부 무료 템플릿 찾아줘',
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
      <PostingStepHeader title="공고 디자인" caption="Poster">
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
            void persist(design, JSON.stringify(design) !== savedDesignRef.current).then((ok) => {
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
            onClick={() => void persist(design, true)}
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
              void persist(design, JSON.stringify(design) !== savedDesignRef.current).then((ok) => {
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
            {(proposal?.canvaDesigns?.length ?? 0) > 0 && (
              <section aria-label="Canva 디자인 검색 결과" className="space-y-3">
                {importError && (
                  <p role="alert" className="text-xs text-destructive">
                    {importError}
                  </p>
                )}
                <h3 className="text-xs font-semibold">내 Canva 디자인</h3>
                <p className="text-xs text-muted-foreground">
                  배경과 글 영역을 가져와 현재 공고로 채워요. 문구·배치는 채팅으로 수정할 수 있어요.
                </p>
                {proposal?.canvaDesigns?.slice(0, 3).map((item) => (
                  <div key={item.id} className="rounded-lg border bg-background p-3">
                    {item.thumbnailUrl && (
                      <img
                        className="mb-2 h-36 w-full object-contain"
                        src={item.thumbnailUrl}
                        alt={`${item.name} 미리보기`}
                      />
                    )}
                    <p className="text-sm font-medium">{item.name}</p>
                    <a
                      className="text-xs text-muted-foreground underline"
                      href={item.editUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Canva
                    </a>
                    <Button
                      className="mt-3 w-full"
                      size="sm"
                      disabled={busy}
                      onClick={() => void importCanva(item.id)}
                    >
                      {importing ? '가져오는 중…' : '현재 공고로 가져오기'}
                    </Button>
                  </div>
                ))}
              </section>
            )}
            {(proposal?.templates?.length ?? 0) > 0 && (
              <section aria-label="외부 템플릿" className="space-y-3">
                <h3 className="text-xs font-semibold">외부 템플릿</h3>
                <p className="text-xs text-muted-foreground">
                  선택한 테마의 배색과 구성을 현재 공고 길이에 맞춰 적용해요. 원본 문구는 가져오지
                  않아요.
                </p>
                {proposal?.templates?.map((template) => (
                  <div key={template.id} className="rounded-lg border bg-background p-3">
                    <img
                      className="mb-2 h-28 w-full bg-white object-contain"
                      src={
                        template.thumbnailUrl ||
                        `data:image/svg+xml;charset=utf-8,${encodeURIComponent(template.svg)}`
                      }
                      alt={`${template.name} 원본 미리보기`}
                    />
                    <p className="text-sm font-medium">{template.name}</p>
                    <a
                      className="text-xs text-muted-foreground underline"
                      href={template.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      출처 · {template.license}
                    </a>
                    <Button
                      className="mt-3 w-full"
                      size="sm"
                      disabled={busy}
                      onClick={() => void importTemplate(template)}
                    >
                      {importing ? '가져오는 중…' : '공고에 적용'}
                    </Button>
                  </div>
                ))}
              </section>
            )}
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
                      <strong className="text-xs">{proposalName(item.design)}</strong>
                      <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                        {item.reason}
                      </p>
                      {proposal.recommendations.length > 1 && (
                        <div className="mt-2 flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setPreview(item.design)
                              setSmallPane('poster')
                            }}
                            disabled={busy}
                            aria-pressed={preview === item.design}
                          >
                            이 디자인 보기
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-xs text-ai">
                  가운데 포스터의 보라색 테두리에서 변경 내용을 확인해 주세요.
                </p>
                <Button
                  size="sm"
                  className="mt-2"
                  disabled={busy || !preview}
                  onClick={() => {
                    if (preview) void applyRecommendation(preview)
                  }}
                >
                  적용
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() => {
                    setProposal(null)
                    setPreview(null)
                  }}
                >
                  되돌리기
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
                    aria-pressed={!design.canvasJson && design.template === item.id}
                    onClick={() => update({ template: item.id, enabled: true, canvasJson: null })}
                    className={cn(
                      'overflow-hidden rounded-md border text-left disabled:cursor-default',
                      !design.canvasJson && design.template === item.id
                        ? 'border-foreground ring-1 ring-foreground'
                        : 'hover:border-foreground/40',
                    )}
                  >
                    <PosterThumbnail
                      posting={posting}
                      design={{ ...design, template: item.id, enabled: true, canvasJson: null }}
                      logoUrl={logoUrl}
                      compact
                    />
                    <div className="border-t bg-background px-2 py-2">
                      <strong className="block text-center text-[11px]">{item.name}</strong>
                      <span className="sr-only">{item.description}</span>
                    </div>
                  </button>
                ))}
                {(brand.data?.templates ?? []).map((item) => (
                  <div key={item.id} className="group relative">
                    <button
                      type="button"
                      disabled={!editable || busy}
                      aria-pressed={samePosterCanvas(item.canvasJson, design.canvasJson)}
                      className={cn(
                        'w-full overflow-hidden rounded-md border text-left disabled:cursor-default',
                        samePosterCanvas(item.canvasJson, design.canvasJson)
                          ? 'border-foreground ring-1 ring-foreground'
                          : 'hover:border-foreground/40',
                      )}
                      onClick={() =>
                        update({
                          template:
                            POSTER_TEMPLATES.find((base) => base.id === item.template)?.id ??
                            'CLASSIC',
                          decoration: item.decoration,
                          canvasJson: item.canvasJson ?? null,
                          enabled: true,
                        })
                      }
                    >
                      <PosterThumbnail
                        posting={posting}
                        design={{
                          ...design,
                          template:
                            POSTER_TEMPLATES.find((base) => base.id === item.template)?.id ??
                            'CLASSIC',
                          canvasJson: item.canvasJson ?? null,
                          enabled: true,
                        }}
                        logoUrl={logoUrl}
                        compact
                      />
                      <div className="border-t bg-background px-2 py-2">
                        <strong className="block text-center text-[11px]">{item.name}</strong>
                      </div>
                    </button>
                    <PosterTemplateDelete
                      id={item.id}
                      name={item.name}
                      disabled={busy}
                      onDeleted={(savedBrand) => {
                        if (
                          posterAfterTemplateDeletion(design, item, savedBrand) !== design ||
                          (preview &&
                            posterAfterTemplateDeletion(preview, item, savedBrand) !== preview)
                        ) {
                          setPreview(null)
                          setProposal(null)
                        }
                        setDesign((current) =>
                          posterAfterTemplateDeletion(current, item, savedBrand),
                        )
                      }}
                    />
                  </div>
                ))}
              </div>
            </section>
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
                changes={changes}
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
