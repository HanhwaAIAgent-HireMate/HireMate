import { ArrowLeft, ArrowRight, FileDown, LoaderCircle, Trash2 } from 'lucide-react'
import { useEffect, useEffectEvent, useMemo, useRef, useState } from 'react'
import { skipToken, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Skeleton } from '@/components/ui/skeleton'
import { PosterTemplateDelete } from '@/features/company/PosterTemplateDelete'
import { AiRequestPanel, type AiMessage } from '@/features/posting/AiRequestPanel'
import type { ChatStep } from '@/features/chat/steps'
import { errorReply } from '@/features/posting/errorReply'
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
import { useOrshotPoster } from '@/features/posting/useOrshotPoster'
import { useSaveDraftOnLeave } from '@/features/posting/useSaveDraftOnLeave'
import { posterPreviewChanges } from '@/features/posting/poster-preview'
import {
  importPosterTemplate,
  importCanvaPoster,
  importOrshotPoster,
  readPosterCanvas,
  samePosterCanvas,
  sameImportedArtwork,
  posterAfterTemplateDeletion,
  nextExternalTemplateName,
  upgradeCanvaPoster,
  prepareTemplatedRegistration,
  type FreeTemplate,
} from '@/features/posting/poster-canvas'
import type { Schemas } from '@/lib/api/client'
import { api, unwrap, errorMessage, ApiError } from '@/lib/api/client'
import { cn } from '@/lib/utils'
import { nativeRegions, importNativePoster } from '@/features/posting/poster-layout'
import { assertTemplatedPreview } from '@/features/posting/templated-poster-check'

type PosterChatTurn = Schemas['PosterTurn'] & Pick<AiMessage, 'steps' | 'seconds' | 'admin'>

type PosterChatJob = {
  startedAt: number
  steps: ChatStep[]
  completion?: { turn: PosterChatTurn; proposal?: PosterProposal }
}

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

function proposalProvider(design: PosterDesign) {
  if (!design.canvasJson) return '기본 템플릿'
  const source = readPosterCanvas(design.canvasJson).source
  if (source.id?.startsWith('orshot:')) return 'Orshot'
  if (
    source.id?.startsWith('templated:') ||
    readPosterCanvas(design.canvasJson).registeredTemplatedId
  )
    return 'Templated'
  if (source.id?.startsWith('canva:')) return 'Canva'
  return source.url === 'hiremate:generated' ? '자체 생성' : '기본 SVG 양식'
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
  const save = useSavePoster(posting.recruitmentId)
  const ai = usePosterAi(posting.recruitmentId)
  const editable = posting.status === 'DRAFT'
  const recovery = usePostingRecovery(
    `${posting.recruitmentId}:poster`,
    posting.poster ?? initialPoster(),
    editable,
  )
  const { value: storedDesign, setValue: setDesign } = recovery
  const logoFileId = brand.data?.logoFileId
  const design = useMemo(
    () =>
      editable && logoFileId && !storedDesign.logoFileId
        ? { ...storedDesign, logoFileId, showLogo: true }
        : storedDesign,
    [editable, logoFileId, storedDesign],
  )
  const { value: postingTemplates, setValue: setPostingTemplates } = usePostingRecovery<
    Schemas['PosterTemplate'][]
  >(`${posting.recruitmentId}:poster-templates`, [], editable, false)
  const templateChoices = useMemo(() => {
    const choices = [...(brand.data?.templates ?? []), ...postingTemplates]
    if (
      design.canvasJson &&
      !choices.some((item) => samePosterCanvas(item.canvasJson, design.canvasJson))
    ) {
      const source = readPosterCanvas(design.canvasJson).source
      if (
        !choices.some(
          (item) => item.canvasJson && readPosterCanvas(item.canvasJson).source.id === source.id,
        )
      )
        choices.push({
          id: 'current-posting',
          name: source.name,
          template: design.template,
          mood: design.mood,
          color: design.color,
          decoration: design.decoration,
          canvasJson: design.canvasJson,
        })
    }
    return choices
  }, [brand.data?.templates, postingTemplates, design])
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
  const { value: storedHistory, setValue: setStoredHistory } = usePostingRecovery<PosterChatTurn[]>(
    `${posting.recruitmentId}:poster-chat`,
    [],
    editable,
    false,
  )
  const queryClient = useQueryClient()
  const historyKey = ['poster-chat-history', posting.postingId] as const
  const { data: cachedHistory } = useQuery<PosterChatTurn[]>({
    queryKey: historyKey,
    queryFn: skipToken,
    gcTime: 30 * 60 * 1000,
  })
  const history = cachedHistory ?? storedHistory
  const setHistory = (
    next: PosterChatTurn[] | ((previous: PosterChatTurn[]) => PosterChatTurn[]),
  ) => {
    const previous = queryClient.getQueryData<PosterChatTurn[]>(historyKey) ?? storedHistory
    const turns = typeof next === 'function' ? next(previous) : next
    queryClient.setQueryData(historyKey, turns)
    setStoredHistory(turns)
  }
  const chatKey = ['poster-chat-job', posting.postingId] as const
  const { data: chatJob } = useQuery<PosterChatJob | null>({
    queryKey: chatKey,
    queryFn: skipToken,
    gcTime: 30 * 60 * 1000,
  })
  const chatPending = Boolean(chatJob)
  const messages: AiMessage[] = history.map((turn) => ({
    role: turn.role === 'USER' ? 'user' : 'ai',
    text: turn.text,
    steps: turn.steps,
    seconds: turn.seconds,
    admin: turn.admin,
    agent: turn.role === 'ASSISTANT' && !turn.admin ? 'Posting Agent' : undefined,
  }))
  const [proposal, setProposal] = useState<PosterProposal | null>(null)
  const [preview, setPreview] = useState<PosterDesign | null>(null)
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [smallPane, setSmallPane] = useState<'options' | 'poster' | 'chat'>('poster')
  const poster = useRef<HTMLDivElement>(null)
  const recommended = useRef(false)
  const shown = preview ?? design
  const currentSource = useMemo(() => {
    try {
      return design.canvasJson ? readPosterCanvas(design.canvasJson).source : null
    } catch {
      return null
    }
  }, [design.canvasJson])
  const refreshedOrshot = useOrshotPoster(posting, design)
  useEffect(() => {
    const canvasJson = refreshedOrshot.design.canvasJson
    if (!canvasJson || canvasJson === design.canvasJson) return
    setDesign((current) =>
      current.canvasJson === design.canvasJson
        ? { ...current, canvasJson, motion: 'NONE' }
        : current,
    )
  }, [refreshedOrshot.design.canvasJson, design.canvasJson, setDesign])
  const busy = save.isPending || chatPending || importing || refreshedOrshot.isFetching
  const appliedSources = new Set(
    [design.canvasJson, ...(brand.data?.templates?.map((item) => item.canvasJson) ?? [])].flatMap(
      (canvas) => {
        if (!canvas) return []
        try {
          const id = readPosterCanvas(canvas).source.id
          return id ? [id] : []
        } catch {
          return []
        }
      },
    ),
  )
  const availableTemplates =
    proposal?.templates?.filter((item) => !appliedSources.has(item.id)) ?? []
  const availableCanvaDesigns =
    proposal?.canvaDesigns?.filter((item) => !appliedSources.has(`canva:${item.id}`)) ?? []
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
  const update = (patch: Partial<PosterDesign>) => {
    setPreview(null)
    setProposal(null)
    setDesign({ ...design, ...patch })
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
  const prepareCandidate = async (template: FreeTemplate): Promise<PosterDesign> => {
    let canvasJson: string
    if (template.id.startsWith('orshot:')) {
      if (
        template.sourceUrl !== 'https://orshot.com/templates/' ||
        template.license !== 'Orshot 계정 디자인'
      ) {
        throw new Error('Orshot 출처를 확인하지 못했어요.')
      }
      const imported = await unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/poster/orshot-import', {
          params: { path: { recruitmentId: posting.recruitmentId } },
          body: { templateId: Number(template.id.slice('orshot:'.length)) },
        }),
      )
      canvasJson = await importOrshotPoster(
        { ...imported, name: template.name },
        design.color,
        true,
        posting,
      )
    } else if (template.id.startsWith('templated:') && nativeRegions(template.svg).length > 1) {
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
    const canvas = readPosterCanvas(canvasJson)
    await assertTemplatedPreview(posting, { ...design, canvasJson })
    return {
      ...design,
      enabled: true,
      canvasJson,
      color: canvas.brandColor ?? design.color,
      motion: template.id.startsWith('orshot:') ? 'NONE' : canvas.media ? 'WAVE' : 'NONE',
    }
  }

  const request = async (message: string, automatic = false) => {
    if (queryClient.getQueryData(chatKey)) return
    const current = preview ?? design
    const startedAt = Date.now()
    const steps: ChatStep[] = []
    queryClient.setQueryData<PosterChatJob>(chatKey, { startedAt, steps: [] })
    const updateJob = (patch: Partial<PosterChatJob>) =>
      queryClient.setQueryData<PosterChatJob>(chatKey, (job) =>
        job?.startedAt === startedAt ? { ...job, ...patch } : job,
      )
    const publishSteps = () => updateJob({ steps: [...steps] })
    const processing = () => ({
      steps: [...steps],
      seconds: Math.floor((Date.now() - startedAt) / 1000),
    })
    if (!automatic) {
      setHistory((previous) =>
        [
          ...previous,
          {
            role: 'USER' as const,
            text: message,
            design: current,
            recommendations: [],
            templates: [],
          },
        ].slice(-12),
      )
    }
    try {
      const result = await ai.mutateAsync({
        message,
        design: current,
        history: history.map((turn) => ({
          role: turn.role,
          text: turn.text,
          design: turn.design,
          recommendations: turn.recommendations,
          templates: turn.templates,
        })),
        sectionNames: sectionNames(poster.current),
        onStep: (step) => {
          steps.push(step)
          publishSteps()
        },
      })
      if (queryClient.getQueryData<PosterChatJob>(chatKey)?.startedAt !== startedAt) return
      let registrationNote = ''
      for (const item of result.recommendations) {
        if (!item.design.canvasJson) continue
        const canvas = readPosterCanvas(item.design.canvasJson)
        if (!canvas.templatedRegistration) continue
        steps.push({ text: '새 양식을 등록하고 다시 불러오고 있어요', depth: 0 })
        publishSteps()
        try {
          const request = await prepareTemplatedRegistration(posting, item.design)
          const saved = await unwrap(
            api.POST('/api/recruitments/{recruitmentId}/posting/poster/templated-register', {
              params: { path: { recruitmentId: posting.recruitmentId } },
              body: request,
            }),
          )
          if (!saved.id?.startsWith('templated:')) throw new Error('등록 결과를 확인하지 못했어요.')
          canvas.registeredTemplatedId = saved.id
          canvas.source.name = saved.name || canvas.source.name
        } catch (error) {
          const code = error instanceof ApiError ? error.code : ''
          registrationNote =
            code === 'TEMPLATED_TEMPLATE_LIMIT'
              ? ' Templated의 등록 권한 또는 템플릿 저장 한도를 확인해 주세요. 만든 디자인은 자체 생성 후보로 보여드려요.'
              : code === 'TEMPLATED_NOT_CONFIGURED'
                ? ' Templated 키가 없어 만든 디자인을 자체 생성 후보로 보여드려요.'
                : ' Templated 등록을 완료하지 못해 만든 디자인을 자체 생성 후보로 보여드려요.'
        }
        delete canvas.templatedRegistration
        item.design = { ...item.design, canvasJson: JSON.stringify(canvas) }
      }
      const candidates = result.templates ?? []
      if (candidates.length) {
        steps.push({ text: '후보에 공고 내용을 채워 미리보기를 준비하고 있어요', depth: 0 })
        publishSteps()
        const prepared = await Promise.allSettled(candidates.map(prepareCandidate))
        const failed: FreeTemplate[] = []
        prepared.forEach((item, index) => {
          if (item.status === 'fulfilled') {
            result.recommendations.push({
              design: item.value,
              reason: '현재 공고 내용을 채운 미리보기예요. 비교한 뒤 선택해 주세요.',
            })
          } else failed.push(candidates[index])
        })
        result.templates = failed
        const count = result.recommendations.length
        result.reply = count
          ? `공고 내용을 채운 디자인 ${count}개를 준비했어요. 비교한 뒤 선택해 주세요.${failed.length ? ` ${failed.length}개는 미리보기를 준비하지 못해 원본 후보로 남겼어요.` : ''}`
          : '공고 내용을 채운 미리보기를 준비하지 못했어요. 원본 후보에서 다시 불러올 수 있어요.'
      }
      result.reply += registrationNote
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
        const generated =
          canvas.source.url === 'hiremate:generated' && !canvas.registeredTemplatedId
        const name =
          (canvas.source.id && knownNames.get(canvas.source.id)) ||
          nextExternalTemplateName(names, generated ? '생성템플릿' : '외부템플릿')
        names.push(name)
        canvas.source.name = name
        return { ...item, design: { ...item.design, canvasJson: JSON.stringify(canvas) } }
      })
      updateJob({
        steps,
        completion: {
          proposal: result,
          turn: {
            role: 'ASSISTANT',
            text: result.reply,
            design: null,
            recommendations: result.recommendations,
            templates: result.templates ?? [],
            ...processing(),
          },
        },
      })
    } catch (error) {
      const reply = errorReply(error)
      updateJob({
        steps,
        completion: {
          turn: {
            role: 'ASSISTANT',
            text: reply.text,
            design: null,
            recommendations: [],
            templates: [],
            admin: reply.admin,
            ...processing(),
          },
        },
      })
    }
  }
  const completeChat = useEffectEvent(() => {
    const completion = queryClient.getQueryData<PosterChatJob>(chatKey)?.completion
    if (!completion) return
    queryClient.setQueryData(chatKey, null)
    setHistory((previous) => [...previous, completion.turn].slice(-12))
    const result = completion.proposal
    if (!result) return
    setProposal(result)
    setPreview(
      result.recommendations.length === 1 &&
        !result.templates?.length &&
        !result.canvaDesigns?.length
        ? result.recommendations[0].design
        : null,
    )
    if (result.recommendations.length) setSmallPane('poster')
  })
  useEffect(() => {
    if (chatJob?.completion) queueMicrotask(() => completeChat())
  }, [chatJob])
  const recommend = useEffectEvent(() => {
    void request('회사 소개와 문화, 공고 분량에 맞는 포스터 템플릿 2종을 추천해줘.', true)
  })
  useEffect(() => {
    if (recommended.current || !editable || posting.poster?.enabled || history.length || chatJob)
      return
    recommended.current = true
    recommend()
  }, [editable, posting.poster?.enabled, history.length, chatJob])
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

  const previewImported = (next: PosterDesign) => {
    setPreview(next)
    setProposal((current) => ({
      reply: '미리보기를 확인한 뒤 적용해 주세요.',
      templates: current?.templates ?? [],
      selectedTemplateId: null,
      canvaQuery: null,
      canvaDesigns: current?.canvaDesigns ?? [],
      externalQuery: null,
      candidateMode: null,
      recommendations: [{ design: next, reason: '아직 적용하지 않은 미리보기예요.' }],
    }))
    setSmallPane('poster')
  }

  const applyOrshotOriginal = async (sourceId: string, name: string) => {
    setImporting(true)
    try {
      const imported = await unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/poster/orshot-import', {
          params: { path: { recruitmentId: posting.recruitmentId } },
          body: { templateId: Number(sourceId.slice('orshot:'.length)) },
        }),
      )
      const canvasJson = await importOrshotPoster(
        { ...imported, name },
        design.color,
        true,
        posting,
      )
      const next = {
        ...design,
        enabled: true,
        canvasJson,
        color: readPosterCanvas(canvasJson).brandColor ?? design.color,
        motion: 'NONE' as const,
      }
      previewImported(next)
      toast.info('미리보기를 준비했어요. 적용을 누르면 템플릿 목록에 추가돼요.')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setImporting(false)
    }
  }

  const importTemplate = async (template: FreeTemplate) => {
    if (template.id.startsWith('orshot:')) {
      if (
        template.sourceUrl !== 'https://orshot.com/templates/' ||
        template.license !== 'Orshot 계정 디자인'
      ) {
        toast.error('Orshot 출처를 확인하지 못했어요.')
        return
      }
      await applyOrshotOriginal(template.id, template.name)
      return
    }
    setImporting(true)
    try {
      const saved = brand.data?.templates.find((item) => {
        try {
          return item.canvasJson && readPosterCanvas(item.canvasJson).source.id === template.id
        } catch {
          return false
        }
      })
      if (saved?.canvasJson) {
        previewImported({ ...design, enabled: true, canvasJson: saved.canvasJson })
        return
      }
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
      await assertTemplatedPreview(posting, { ...design, canvasJson })
      const source = readPosterCanvas(canvasJson).source
      const existing = brand.data?.templates.find((item) => {
        if (!item.canvasJson) return false
        try {
          const saved = readPosterCanvas(item.canvasJson).source
          return (
            (saved.id ? saved.id === source.id : saved.name === source.name) ||
            sameImportedArtwork(item.canvasJson, canvasJson)
          )
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
      previewImported({
        ...design,
        enabled: true,
        canvasJson: existing?.canvasJson ?? canvasJson,
        motion: document.media && design.motion === 'NONE' ? 'WAVE' : design.motion,
      })
      toast.info('미리보기를 준비했어요. 적용을 누르면 템플릿 목록에 추가돼요.')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setImporting(false)
    }
  }

  const applyRecommendation = (next: PosterDesign) => {
    try {
      if (next.canvasJson) {
        const canvas = readPosterCanvas(next.canvasJson)
        if (
          !templateChoices.some((item) =>
            canvas.source.id && item.canvasJson
              ? readPosterCanvas(item.canvasJson).source.id === canvas.source.id
              : samePosterCanvas(item.canvasJson, next.canvasJson),
          )
        ) {
          if (canvas.source.url !== 'hiremate:generated') {
            canvas.source.name = nextExternalTemplateName(templateChoices.map((item) => item.name))
            next = { ...next, canvasJson: JSON.stringify(canvas) }
          }
          const saved = {
            id: canvas.source.id || crypto.randomUUID(),
            name: canvas.source.name,
            template: next.template,
            mood: next.mood,
            decoration: next.decoration,
            color: next.color,
            canvasJson: next.canvasJson,
          }
          setPostingTemplates((current) => [...current, saved])
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
      const saved = brand.data?.templates.find((item) => {
        try {
          return (
            item.canvasJson && readPosterCanvas(item.canvasJson).source.id === `canva:${designId}`
          )
        } catch {
          return false
        }
      })
      if (saved?.canvasJson) {
        previewImported({ ...design, canvasJson: saved.canvasJson, enabled: true })
        return
      }
      const imported = await unwrap(
        api.POST('/api/recruitments/{recruitmentId}/posting/poster/canva-import', {
          params: { path: { recruitmentId: posting.recruitmentId } },
          body: { designId },
        }),
      )
      const canvasJson = await importCanvaPoster(imported, posting, design.color)
      const duplicate = brand.data?.templates.find((item) =>
        sameImportedArtwork(item.canvasJson, canvasJson),
      )
      if (duplicate?.canvasJson) {
        previewImported({ ...design, canvasJson: duplicate.canvasJson, enabled: true })
        return
      }
      const name = nextExternalTemplateName(brand.data?.templates.map((item) => item.name) ?? [])
      const document = readPosterCanvas(canvasJson)
      document.source.name = name
      const namedCanvas = JSON.stringify(document)
      previewImported({ ...design, canvasJson: namedCanvas, enabled: true })
      toast.info('미리보기를 준비했어요. 적용을 누르면 템플릿 목록에 추가돼요.')
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
        '회사 특징을 살린 서로 다른 포스터 템플릿 3개 만들어줘',
        '금융권에 어울리는 외부 무료 템플릿 찾아줘',
        '움직이는 포스터 템플릿 추천해줘',
        '우리는 더 고급스러운 느낌이 있어야 해',
        '장식 없이 깔끔하게 정리해줘',
        '회사 소개에 어울리는 디자인을 추천해줘',
        '실무면접 아이콘을 사람 아이콘으로 바꿔줘',
      ]}
      hint="분위기와 장식은 이곳에서 요청해 주세요. AI 수정안은 적용해야 반영돼요."
      pending={chatPending || importing}
      steps={
        chatPending
          ? chatJob?.steps
          : importing
            ? [{ text: '공고 내용을 채운 미리보기를 준비하고 있어요', depth: 0 }]
            : undefined
      }
      disabled={busy}
      onSend={(message) => void request(message)}
      onReset={() => {
        if (busy) return
        recommended.current = true
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
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {(importing || refreshedOrshot.isFetching) && (
          <div className="absolute inset-0 z-10 grid place-items-center bg-background/60 p-4">
            <div
              role="status"
              className="flex items-center gap-3 rounded-lg border bg-background p-4 shadow-sm"
            >
              <LoaderCircle
                aria-hidden="true"
                className="size-5 shrink-0 motion-safe:animate-spin"
              />
              <div>
                <p className="text-sm font-medium">공고를 채운 미리보기 준비 중…</p>
                <p className="text-xs text-muted-foreground">
                  배경과 공고 내용을 불러오는 중이에요.
                </p>
              </div>
            </div>
          </div>
        )}
        <aside
          aria-label="디자인 옵션"
          className={cn(
            'min-h-0 w-full shrink-0 flex-col border-r bg-background lg:flex lg:w-[272px] xl:w-[296px]',
            smallPane === 'options' ? 'flex' : 'hidden',
          )}
        >
          <div className="flex h-12 shrink-0 items-center justify-between border-b px-4">
            <h2 className="text-sm font-semibold">디자인 옵션</h2>
          </div>
          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-4">
            {refreshedOrshot.isError && (
              <div role="alert" className="rounded-md border p-3 text-xs">
                <p>공고 변경 내용을 Orshot 원본에 반영하지 못했어요.</p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2"
                  onClick={() => void refreshedOrshot.refetch()}
                >
                  다시 시도
                </Button>
              </div>
            )}
            {availableCanvaDesigns.length > 0 && (
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
                {availableCanvaDesigns.slice(0, 3).map((item) => (
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
                      {importing ? '불러오는 중…' : '선택'}
                    </Button>
                  </div>
                ))}
              </section>
            )}
            {availableTemplates.length > 0 && (
              <section aria-label="외부 템플릿" className="space-y-3">
                <h3 className="text-xs font-semibold">외부 템플릿</h3>
                <p className="text-xs text-muted-foreground">
                  선택한 테마의 배색과 구성을 현재 공고 길이에 맞춰 적용해요. 원본 문구는 가져오지
                  않아요.
                </p>
                {availableTemplates.map((template) => (
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
                      {importing ? '불러오는 중…' : '선택'}
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
                      {proposal.recommendations.length > 1 && (
                        <div className="mb-2 overflow-hidden rounded border">
                          <PosterThumbnail
                            posting={posting}
                            design={item.design}
                            logoUrl={logoUrl}
                            compact
                          />
                        </div>
                      )}
                      <strong className="text-xs">{proposalName(item.design)}</strong>
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {proposalProvider(item.design)}
                      </p>
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
              {editable && currentSource?.id?.startsWith('orshot:') && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mb-3 w-full"
                  disabled={busy}
                  onClick={() => void applyOrshotOriginal(currentSource.id!, currentSource.name)}
                >
                  Orshot 원본 다시 적용
                </Button>
              )}
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
                {templateChoices.map((item) => (
                  <div key={item.id} className="group relative">
                    <button
                      type="button"
                      disabled={!editable || busy}
                      aria-pressed={
                        samePosterCanvas(item.canvasJson, design.canvasJson) ||
                        (!!currentSource?.id &&
                          !!item.canvasJson &&
                          readPosterCanvas(item.canvasJson).source.id === currentSource.id)
                      }
                      className={cn(
                        'w-full overflow-hidden rounded-md border text-left disabled:cursor-default',
                        samePosterCanvas(item.canvasJson, design.canvasJson) ||
                          (!!currentSource?.id &&
                            !!item.canvasJson &&
                            readPosterCanvas(item.canvasJson).source.id === currentSource.id)
                          ? 'border-foreground ring-1 ring-foreground'
                          : 'hover:border-foreground/40',
                      )}
                      onClick={() => {
                        const sourceId = item.canvasJson
                          ? readPosterCanvas(item.canvasJson).source.id
                          : undefined
                        if (sourceId?.startsWith('orshot:')) {
                          update({
                            template:
                              POSTER_TEMPLATES.find((base) => base.id === item.template)?.id ??
                              'CLASSIC',
                            decoration: item.decoration,
                            canvasJson: item.canvasJson,
                            enabled: true,
                            motion: 'NONE',
                          })
                          return
                        }
                        update({
                          template:
                            POSTER_TEMPLATES.find((base) => base.id === item.template)?.id ??
                            'CLASSIC',
                          decoration: item.decoration,
                          canvasJson: item.canvasJson ?? null,
                          enabled: true,
                        })
                      }}
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
                    {brand.data?.templates.some((saved) => saved.id === item.id) ? (
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
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        aria-label={`${item.name} 템플릿 삭제`}
                        disabled={busy}
                        className="absolute top-1.5 right-1.5 z-10 size-6 rounded-full bg-background shadow-sm [&_svg]:size-3.5"
                        onClick={() => {
                          setPostingTemplates((current) =>
                            current.filter((saved) => saved.id !== item.id),
                          )
                          const savedBrand = brand.data
                          if (savedBrand)
                            setDesign((current) =>
                              posterAfterTemplateDeletion(current, item, savedBrand),
                            )
                          setPreview(null)
                          setProposal(null)
                        }}
                      >
                        <Trash2 />
                      </Button>
                    )}
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
            </fieldset>
          </div>
        </aside>
        <ResizablePanelGroup
          id="poster-editor"
          className={cn('min-w-0 flex-1 lg:flex', smallPane === 'options' ? 'hidden' : 'flex')}
        >
          <ResizablePanel
            id="poster-preview"
            minSize={420}
            className={cn(smallPane === 'poster' ? 'flex' : 'hidden', 'lg:flex')}
          >
            <section
              aria-label="포스터 미리보기"
              className="flex h-full min-h-0 w-full min-w-0 flex-col bg-surface/60"
            >
              <div className="flex h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b px-5 text-xs text-muted-foreground">
                <span>{preview ? 'AI 수정안 미리보기' : '포스터 미리보기'}</span>
                {/* 켜져 있는 평소 상태는 따로 적지 않는다. 적용 전 수정안과 포스터를 끈 때만 알린다 */}
                {(preview || !shown.enabled) && (
                  <span>{preview ? '적용 전' : '포스터 사용 안 함'}</span>
                )}
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
          </ResizablePanel>
          {editable && (
            <>
              <ResizableHandle
                withHandle
                aria-label="AI 수정 요청 너비 조절"
                className="hidden lg:flex"
              />
              <ResizablePanel
                id="poster-ai-request"
                defaultSize={300}
                minSize={280}
                groupResizeBehavior="preserve-pixel-size"
                aria-label="포스터 AI 챗"
                className={cn('min-h-0 lg:flex', smallPane === 'chat' ? 'flex' : 'hidden')}
              >
                {chatPanel}
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      </div>
    </>
  )
}
