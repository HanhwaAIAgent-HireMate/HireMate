import { ArrowRight, FileText, Lock, Settings, X } from 'lucide-react'
import { useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { addStep, type ChatStep } from '@/features/chat/steps'
import { AiRequestPanel, type AiMessage } from '@/features/posting/AiRequestPanel'
import {
  useApplySuggestion,
  useDiscardSuggestion,
  usePostingAiRequest,
  useSavePosting,
  useSaveStages,
  type Posting,
  type PostingContent,
} from '@/features/posting/api'
import { BulletListField, LineBullet } from '@/features/posting/BulletListField'
import { focusLabel, hasLine, toServerFocus, type LineFocus } from '@/features/posting/focus'
import { StageEditor } from '@/features/posting/StageEditor'
import { StageFlow } from '@/features/posting/StageFlow'
import { PostingStepHeader } from '@/features/posting/PostingStepHeader'
import {
  followLines,
  isRequiredKey,
  REQUIRED_KEYS,
  type RequiredKey,
} from '@/features/posting/required'
import { usePostingRecovery } from '@/features/posting/usePostingRecovery'
import { stagesProblem, toStageForms, type StageForm } from '@/features/posting/stages'
import {
  CAREER_KINDS,
  EMPLOYMENT_TYPES,
  MAX_CAREER_YEARS,
  careerLevel,
  formatCareer,
  parseCareer,
  toCareerYears,
  type CareerKind,
  type CareerLevel,
  MAX_HEADCOUNT,
  toHeadcount,
  WORK_FIELDS,
  WORK_KEYS,
} from '@/features/posting/conditions'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const EXAMPLES = [
  '우대 사항에 결제·정산 경험을 더 구체적으로 써줘',
  '전형은 서류, 직무역량 평가, 개발 과제, 1차 실무면접, 최종면접 순으로 해줘',
  '포트폴리오도 필수로 받아줘',
]

const TAGS: {
  key: 'jobCategory' | 'employmentType' | 'career' | 'education'
  placeholder: string
}[] = [
  { key: 'jobCategory', placeholder: '직무 (예: 개발 › 백엔드)' },
  { key: 'employmentType', placeholder: '고용 형태' },
  { key: 'career', placeholder: '경력 구분' },
  { key: 'education', placeholder: '학력' },
]

type ListKey = 'duties' | 'qualifications' | 'preferred' | 'benefits'

const LISTS: { key: ListKey; label: string }[] = [
  { key: 'duties', label: '주요 업무' },
  { key: 'qualifications', label: '자격 요건' },
  { key: 'preferred', label: '우대 사항' },
]

/** 경력을 바꾼 뒤 [다시 쓰기]로 AI에게 보내는 요청. '다시'가 있어 지금 줄 뒤에 더하지 않고 목록을 새로 쓴다 */
const REWRITE_REQUEST = '자격 요건과 우대 사항을 다시 써 줘'

/** 수정안을 한 덩어리로 처리하는 기본 정보 칸 */
const BASIC_FIELDS = [
  'title',
  'jobCategory',
  'employmentType',
  'career',
  'position',
  'headcount',
  'education',
]

// PST-01 Job Posting Editor. HR이 직접 쓰거나 AI에게 말해 고치고, 바뀐 부분은 HR이 적용 여부를 정한다
export function PostingEditor({
  posting,
  messages,
  setMessages,
  focus,
  setFocus,
  writtenFor,
  setWrittenFor,
  onNext,
}: {
  posting: Posting
  /** 저장 · 적용으로 편집 상태를 새로 열어도 대화와 고른 줄은 남도록 화면이 들고 있다 */
  messages: AiMessage[]
  setMessages: Dispatch<SetStateAction<AiMessage[]>>
  focus: LineFocus | null
  setFocus: Dispatch<SetStateAction<LineFocus | null>>
  /** 경력을 바꾸기 전, 지금 자격 요건 · 우대 사항이 쓰인 기준. 바꾸지 않았거나 안내를 닫으면 null이다 */
  writtenFor: CareerLevel | null
  setWrittenFor: Dispatch<SetStateAction<CareerLevel | null>>
  onNext: () => void
}) {
  const id = posting.recruitmentId
  const contentRecovery = usePostingRecovery(
    `${id}:content`,
    posting.content,
    posting.status === 'DRAFT',
  )
  const { value: draft, setValue: setDraft, dirty } = contentRecovery
  // 전형 절차는 게시 전에 HR이 직접 고친다. 저장하면 전형이 새로 만들어져 안내는 이름으로 이어 받는다
  const stageRecovery = usePostingRecovery(
    `${id}:stages`,
    toStageForms(posting.stages),
    posting.status === 'DRAFT',
  )
  const { value: stages, setValue: setStages, dirty: stagesDirty } = stageRecovery
  // 서류 필수 조건. 지원자에게 보이지 않는 표시라 본문과 따로 들고, 저장할 때 함께 보낸다
  const requiredRecovery = usePostingRecovery(
    `${id}:required`,
    posting.required,
    posting.status === 'DRAFT',
  )
  const { value: required, setValue: setRequired, dirty: requiredDirty } = requiredRecovery
  const [stagesError, setStagesError] = useState<string | null>(null)
  const save = useSavePosting(id)
  const saveStages = useSaveStages(id)
  // 기다리는 동안 받은 Posting Agent의 처리 단계. 요청마다 새로 쌓는다
  const [steps, setSteps] = useState<ChatStep[]>([])
  const ai = usePostingAiRequest(id, (step) => setSteps((current) => addStep(current, step)))
  const apply = useApplySuggestion(id)
  const discard = useDiscardSuggestion(id)
  const saving = save.isPending || saveStages.isPending

  const suggestion = posting.suggestion
  const changed = new Set(suggestion?.changedFields ?? [])
  const isDraft = posting.status === 'DRAFT'
  // 게시한 공고는 모든 지원자가 같은 공고를 보도록 바꿀 수 없다. 전형별 안내(일정 · 장소)는 전형 결과 화면에서 정한다
  const editable = isDraft
  const shown = suggestion ? { ...draft, ...pick(suggestion.content, changed) } : draft
  const locked = (field: string) => !editable || changed.has(field)
  // 고른 줄. 그 칸에 수정안이 생겨 잠기거나 줄이 비면 고르지 않은 것으로 본다
  const picked = focus && !locked(focus.field) && hasLine(focus, draft) ? focus : null

  const update = (patch: Partial<PostingContent>) => {
    setDraft((current) => ({ ...current, ...patch }))
  }

  /** 경력을 바꾸면 처음 바꾸기 전의 기준을 기억해 둔다. 기준이 달라지면 자격 요건 · 우대 사항을 다시 쓸지 묻는다 */
  const changeCareer = (career: string) => {
    if (writtenFor === null) setWrittenFor(careerLevel(draft.career))
    update({ career })
  }
  const hasLists = [...draft.qualifications, ...draft.preferred].some((line) => line.trim())
  const careerNudge =
    editable &&
    writtenFor !== null &&
    careerLevel(draft.career) !== writtenFor &&
    hasLists &&
    !changed.has('qualifications') &&
    !changed.has('preferred')

  /** 줄 앞의 ·을 누르면 그 줄을 고르고, 고른 줄을 다시 누르면 푼다 */
  const toggleFocus = (next: LineFocus) =>
    setFocus(picked?.field === next.field && picked.index === next.index ? null : next)

  /** 고른 칸에서 줄을 더하거나 지우면 줄 순서가 바뀌어 고르기를 푼다 */
  const changeList = (key: ListKey, items: string[]) => {
    if (focus?.field === key && items.length !== draft[key].length) setFocus(null)
    if (key === 'qualifications' || key === 'preferred') {
      setRequired((current) => ({
        ...current,
        [key]: followLines(current[key], draft[key], items),
      }))
    }
    update({ [key]: items })
  }

  /** 줄 끝의 [필수]를 누르면 그 줄을 서류 필수 조건으로 켜거나 끈다 */
  const toggleRequired = (key: RequiredKey, index: number) => {
    const line = draft[key][index]
    setRequired((current) => ({
      ...current,
      [key]: current[key].includes(line)
        ? current[key].filter((item) => item !== line)
        : [...current[key], line],
    }))
  }

  const changeStages = (next: StageForm[]) => {
    setStages(next)
    setStagesError(null)
  }

  const saveDraft = async (silent = false) => {
    if (!dirty && !stagesDirty && !requiredDirty) return true
    if (dirty && !draft.title.trim()) {
      toast.error('채용명을 입력해 주세요.')
      return false
    }
    const stageProblem = stagesDirty ? stagesProblem(stages) : null
    if (stageProblem) {
      setStagesError(stageProblem)
      toast.error(stageProblem)
      return false
    }
    try {
      // 본문을 저장하면 편집 화면을 새로 열어, 전형 절차를 먼저 저장한다
      if (stagesDirty) {
        const saved = await saveStages.mutateAsync(
          stages.map((stage) => ({
            name: stage.name.trim(),
            type: stage.type,
            icon: stage.icon ?? null,
          })),
        )
        setStages(toStageForms(saved.stages))
      }
      if (dirty || requiredDirty) {
        await save.mutateAsync({ content: { ...draft, title: draft.title.trim() }, required })
      }
      if (!silent) toast.success('저장했어요.')
      return true
    } catch (error) {
      toast.error(errorMessage(error))
      return false
    }
  }

  const sendRequest = async (message: string) => {
    const target = picked
    // 저장하면 빈 줄이 빠지므로, 저장 전 화면의 줄 순서를 서버의 줄 순서로 바꿔 둔다
    const sent = target && toServerFocus(target, draft)
    setMessages((current) => [
      ...current,
      { role: 'user', text: message, focus: target ? focusLabel(target) : undefined },
    ])
    if (!(await saveDraft(true))) return
    setSteps([])
    try {
      const answer = await ai.mutateAsync({ message, focus: sent })
      // 그 줄의 수정안이 생기면 칸이 잠겨 고르기를 푼다. 아니면 서버의 줄 순서(= 다시 연 화면의 순서)로 남긴다
      if (target && sent) {
        setFocus(
          answer.posting.suggestion?.changedFields.includes(target.field)
            ? null
            : { field: target.field, index: sent.index ?? undefined },
        )
      }
      setMessages((current) => [
        ...current,
        { role: 'ai', text: answer.reply, agent: answer.agent, stub: answer.stub },
      ])
    } catch (error) {
      setMessages((current) => [...current, { role: 'ai', text: errorMessage(error) }])
    }
  }

  /**
   * 수정안을 적용하거나 되돌린다. fields가 있으면 그 덩어리만 처리하고 나머지는 수정안으로 남긴다.
   * 처리한 칸만 서버 값으로 바꿔, 다른 칸에서 고치던 내용은 그대로 둔다
   */
  const resolve = (accept: boolean, fields?: string[]) => {
    const targets = new Set(fields ? fields.filter((field) => changed.has(field)) : changed)
    ;(accept ? apply : discard).mutate(fields && [...targets], {
      onSuccess: (updated) => {
        setDraft({ ...draft, ...pick(updated.content, targets) })
        // AI가 경력만 바꿨으면 화면에서 바꾼 것처럼 기준을 기억한다. 목록도 함께 썼으면 바뀐 경력에 맞춰 쓴 것이다
        if (accept && REQUIRED_KEYS.some((key) => targets.has(key))) {
          setWrittenFor(null)
        } else if (accept && targets.has('career') && writtenFor === null) {
          setWrittenFor(careerLevel(draft.career))
        }
        // AI가 새로 쓴 줄은 필수 표시가 빠진다. 꺼진 표시가 있으면 다시 켤 수 있게 알린다
        const lists = REQUIRED_KEYS.filter((key) => targets.has(key))
        const dropped = lists.reduce(
          (count, key) =>
            count + required[key].filter((line) => !updated.required[key].includes(line)).length,
          0,
        )
        if (lists.length) {
          setRequired({
            ...required,
            ...Object.fromEntries(lists.map((key) => [key, updated.required[key]])),
          })
        }
        if (accept && dropped) {
          toast.info(`AI가 바꾼 줄의 필수 표시 ${dropped}개가 꺼졌어요. 필요하면 다시 켜 주세요.`)
        }
        if (accept && targets.has('stages')) {
          setStages(toStageForms(updated.stages))
        }
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const goPublish = async () => {
    if (await saveDraft(true)) onNext()
  }

  /**
   * 덩어리마다 [적용] [되돌리기]. 기본 정보(채용명 · 직무 · 고용 형태 · 경력 · 직급 · 채용 인원 · 학력)와
   * 근무 조건(근무지 · 근무 요일 · 시간 · 급여)은 각각 한 덩어리로 처리한다
   */
  const actions = (field: string) => {
    let fields = BASIC_FIELDS.includes(field)
      ? BASIC_FIELDS
      : WORK_KEYS.includes(field)
        ? WORK_KEYS
        : [field]
    if (
      changed.has('career') &&
      fields.some((name) => ['career', 'qualifications', 'preferred'].includes(name))
    ) {
      fields = [
        ...new Set([
          ...fields,
          'career',
          ...['qualifications', 'preferred'].filter((name) => changed.has(name)),
        ]),
      ]
    }
    return (
      fields.some((name) => changed.has(name)) && (
        <SuggestionActions
          onApply={() => resolve(true, fields)}
          onDiscard={() => resolve(false, fields)}
        />
      )
    )
  }

  return (
    <div className="flex h-full flex-col">
      <PostingStepHeader title={isDraft ? '공고 작성' : '게시한 공고'}>
        {editable && (
          <Button
            variant="outline"
            className="min-w-20"
            onClick={() => void saveDraft()}
            disabled={!(dirty || stagesDirty || requiredDirty) || saving}
          >
            {isDraft ? '임시 저장' : '저장'}
          </Button>
        )}
        {isDraft ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button
                  className="min-w-20"
                  onClick={() => void goPublish()}
                  disabled={Boolean(suggestion) || saving}
                >
                  다음
                  <ArrowRight />
                </Button>
              </span>
            </TooltipTrigger>
            {suggestion && (
              <TooltipContent>AI 수정안을 적용하거나 되돌린 뒤 게시해요</TooltipContent>
            )}
          </Tooltip>
        ) : (
          <>
            <Button variant="outline" asChild>
              <Link to={`/hr/recruitments/${id}/posting/poster`}>포스터 · PDF</Link>
            </Button>
            <Button asChild>
              <Link to={`/hr/recruitments/${id}/posting/status`}>접수 현황</Link>
            </Button>
          </>
        )}
      </PostingStepHeader>
      {editable && (dirty || stagesDirty || requiredDirty) && (
        <p role="status" className="border-b bg-muted px-6 py-2 text-xs text-muted-foreground">
          {contentRecovery.restored || stageRecovery.restored
            ? '저장하지 않은 편집을 복구했어요. '
            : ''}
          변경 내용은 이 탭에 임시 보관돼요. 공고에 반영하려면 임시 저장을 눌러 주세요.
        </p>
      )}
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto">
          <div className="mx-auto max-w-[760px] space-y-6 px-6 py-6">
            {!isDraft && (
              <div className="flex items-center gap-2 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                <Lock className="size-4 shrink-0" />
                게시한 공고는 바꿀 수 없어요. 전형 일정 · 장소는 전형 결과 화면의 다음 전형 안내에서
                정해요.
              </div>
            )}
            {suggestion && (
              <div className="flex flex-wrap items-center gap-2 rounded-lg bg-pass px-3 py-2 text-sm">
                <span>AI 수정안이 있어요. 초록색 칸마다 적용하거나 되돌릴 수 있어요.</span>
                <div className="ml-auto flex gap-2">
                  <Button size="sm" onClick={() => resolve(true)}>
                    모두 적용
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => resolve(false)}>
                    모두 되돌리기
                  </Button>
                </div>
              </div>
            )}
            <div className="space-y-3">
              <div
                className={cn(
                  'flex items-baseline gap-1.5 text-xl font-bold',
                  changed.has('title') && 'bg-pass',
                )}
              >
                <span className="shrink-0">[{posting.companyName}]</span>
                <input
                  aria-label="채용명"
                  value={shown.title}
                  disabled={locked('title')}
                  onChange={(event) => update({ title: event.target.value })}
                  style={{ width: `calc(${textWidth(shown.title || '채용명') * 0.92}em + 2px)` }}
                  className="max-w-full min-w-0 bg-transparent outline-none"
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {TAGS.map((tag) =>
                  tag.key === 'employmentType' ? (
                    <EmploymentTypeSelect
                      key={tag.key}
                      value={shown.employmentType}
                      disabled={locked(tag.key)}
                      changed={changed.has(tag.key)}
                      onChange={(employmentType) => update({ employmentType })}
                    />
                  ) : tag.key === 'career' ? (
                    <CareerField
                      key={tag.key}
                      value={shown.career}
                      position={shown.position}
                      disabled={locked(tag.key)}
                      changed={changed.has(tag.key) || changed.has('position')}
                      onChange={changeCareer}
                      onPositionChange={(position) => update({ position })}
                    />
                  ) : (
                    <input
                      key={tag.key}
                      aria-label={tag.placeholder}
                      value={shown[tag.key]}
                      placeholder={tag.placeholder}
                      disabled={locked(tag.key)}
                      onChange={(event) => update({ [tag.key]: event.target.value })}
                      style={{
                        width: `calc(${textWidth(shown[tag.key] || tag.placeholder)}em + 1.25rem)`,
                      }}
                      className={cn(
                        'h-7 rounded-md bg-muted px-2 text-xs outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring',
                        changed.has(tag.key) && 'bg-pass',
                      )}
                    />
                  ),
                )}
                <label
                  className={cn(
                    'flex h-7 items-center gap-1 rounded-md bg-muted px-2 text-xs',
                    changed.has('headcount') && 'bg-pass',
                  )}
                >
                  <span className="text-muted-foreground">채용</span>
                  <input
                    aria-label="채용 인원"
                    type="number"
                    min={1}
                    max={MAX_HEADCOUNT}
                    value={shown.headcount ?? ''}
                    placeholder="0"
                    disabled={locked('headcount')}
                    onChange={(event) => update({ headcount: toHeadcount(event.target.value) })}
                    className="w-10 bg-transparent text-right outline-none"
                  />
                  명
                </label>
              </div>
              {actions('title')}
            </div>
            <Section title="근무 조건">
              <div className="space-y-2">
                {WORK_FIELDS.map((field) => (
                  <label key={field.key} className="flex items-center gap-2 text-sm">
                    <span className="w-24 shrink-0 text-xs text-muted-foreground">
                      {field.label}
                    </span>
                    <input
                      aria-label={field.label}
                      value={shown[field.key]}
                      placeholder={field.placeholder}
                      maxLength={field.maxLength}
                      disabled={locked(field.key)}
                      onChange={(event) => update({ [field.key]: event.target.value })}
                      className={cn(
                        'h-8 min-w-0 flex-1 rounded-md bg-muted px-2 outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring',
                        changed.has(field.key) && 'bg-pass',
                      )}
                    />
                  </label>
                ))}
              </div>
              {actions('location')}
            </Section>
            <Section
              title="회사 소개"
              extra={
                <Link
                  to="/hr/settings"
                  className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-normal text-muted-foreground hover:text-foreground"
                >
                  <Settings className="size-3" />
                  설정
                </Link>
              }
            >
              <div
                className={cn(
                  'flex items-start gap-2 rounded px-1 text-sm',
                  picked?.field === 'intro' && 'bg-ai-soft ring-1 ring-ai/40',
                )}
              >
                <LineBullet
                  label="회사 소개"
                  selected={picked?.field === 'intro'}
                  onSelect={locked('intro') ? undefined : () => toggleFocus({ field: 'intro' })}
                />
                <Textarea
                  aria-label="회사 소개"
                  value={shown.intro}
                  disabled={locked('intro')}
                  onChange={(event) => update({ intro: event.target.value })}
                  className="min-h-0 resize-none border-0 p-0 shadow-none focus-visible:ring-0"
                  rows={2}
                />
              </div>
            </Section>
            {LISTS.map((list) => (
              <Section key={list.key} title={list.label} highlighted={changed.has(list.key)}>
                {list.key === 'qualifications' && careerNudge && (
                  <CareerNudge
                    disabled={ai.isPending || saving}
                    onRewrite={() => {
                      setWrittenFor(null)
                      void sendRequest(REWRITE_REQUEST)
                    }}
                    onClose={() => setWrittenFor(null)}
                  />
                )}
                <BulletListField
                  label={list.label}
                  items={shown[list.key]}
                  disabled={locked(list.key)}
                  highlight={
                    changed.has(list.key) ? newLines(shown[list.key], draft[list.key]) : undefined
                  }
                  onChange={(items) => changeList(list.key, items)}
                  selected={picked?.field === list.key ? picked.index : undefined}
                  onSelect={(index) => toggleFocus({ field: list.key, index })}
                  marked={isRequiredKey(list.key) ? new Set(required[list.key]) : undefined}
                  onMark={
                    isRequiredKey(list.key) && editable
                      ? (index) => toggleRequired(list.key as RequiredKey, index)
                      : undefined
                  }
                />
                {actions(list.key)}
              </Section>
            ))}
            <Section title="전형 절차" highlighted={changed.has('stages')}>
              {changed.has('stages') && suggestion?.stages ? (
                <>
                  <StageFlow stages={suggestion.stages} highlight />
                  {actions('stages')}
                </>
              ) : isDraft ? (
                <StageEditor stages={stages} onChange={changeStages} problem={stagesError} />
              ) : (
                <StageFlow stages={posting.stages} />
              )}
            </Section>
            <FixedBox title="필수 제출 서류">
              <div className="flex flex-wrap gap-2">
                {(suggestion?.documents ?? posting.documents)
                  .filter((document) => document.required)
                  .map((document) => {
                    const added = !posting.documents.find(
                      (current) => current.type === document.type,
                    )?.required
                    return (
                      <span
                        key={document.type}
                        className={cn(
                          'inline-flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1 text-xs font-medium',
                          added && 'border-pass-foreground/30 bg-pass text-pass-foreground',
                        )}
                      >
                        <FileText className="size-3.5" />
                        {document.label} {document.format}
                      </span>
                    )
                  })}
              </div>
              {actions('requiredDocuments')}
            </FixedBox>
            <Section title="복지" highlighted={changed.has('benefits')}>
              <BulletListField
                label="복지"
                items={shown.benefits}
                disabled={locked('benefits')}
                onChange={(items) => changeList('benefits', items)}
                selected={picked?.field === 'benefits' ? picked.index : undefined}
                onSelect={(index) => toggleFocus({ field: 'benefits', index })}
              />
              {actions('benefits')}
            </Section>
            <FixedBox title="유의사항">
              {posting.notices.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  설정 › 채용 공고에서 필수 안내 문구를 등록하면 여기에 들어가요.
                </p>
              ) : (
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {posting.notices.map((notice) => (
                    <li key={notice}>· {notice}</li>
                  ))}
                </ul>
              )}
            </FixedBox>
          </div>
        </div>
        <AiRequestPanel
          messages={messages}
          examples={EXAMPLES}
          hint={editable ? '줄 앞의 · 을 누르면 그 줄만 고쳐 달라고 할 수 있어요.' : undefined}
          pending={ai.isPending || save.isPending}
          disabled={!editable}
          focus={picked ? { label: focusLabel(picked), onClear: () => setFocus(null) } : undefined}
          steps={steps}
          onSend={(message) => void sendRequest(message)}
          onReset={() => setMessages([])}
        />
      </div>
    </div>
  )
}

/** 글자 수로 입력칸 너비(em)를 잡는다. 한글은 1em, 나머지는 0.6em 정도다. */
function textWidth(text: string) {
  return [...text].reduce((sum, char) => sum + (/[\u3131-\uD79D]/.test(char) ? 1 : 0.6), 0)
}

function pick(content: PostingContent, fields: Set<string>): Partial<PostingContent> {
  return Object.fromEntries(Object.entries(content).filter(([key]) => fields.has(key)))
}

function newLines(next: string[], current: string[]) {
  return new Set(next.filter((line) => !current.includes(line)))
}

function Section({
  title,
  extra,
  highlighted,
  children,
}: {
  title: string
  extra?: ReactNode
  highlighted?: boolean
  children: ReactNode
}) {
  return (
    <section className={cn('space-y-2', highlighted && 'rounded-lg')}>
      <h2 className="flex items-center gap-2 text-sm font-bold">
        {title}
        {extra}
      </h2>
      {children}
    </section>
  )
}

/** 필수 제출 서류 · 유의사항처럼 HR 요청으로만 바뀌는 고정 칸 */
function FixedBox({
  title,
  note,
  children,
}: {
  title: string
  note?: string
  children: ReactNode
}) {
  return (
    <section className="space-y-3 rounded-xl border bg-muted/40 p-4">
      <h2 className="flex items-center gap-1.5 text-sm font-bold">
        {title}
        <Lock className="size-3.5 text-muted-foreground" />
        {note && <span className="text-xs font-normal text-muted-foreground">{note}</span>}
      </h2>
      {children}
    </section>
  )
}

function SuggestionActions({ onApply, onDiscard }: { onApply: () => void; onDiscard: () => void }) {
  return (
    <div className="flex gap-2 pt-1">
      <Button size="sm" onClick={onApply}>
        적용
      </Button>
      <Button size="sm" variant="outline" onClick={onDiscard}>
        되돌리기
      </Button>
    </div>
  )
}

/**
 * 고용 형태는 정해 둔 넷 중에서 고른다. 예전에 글로 적은 값은 지우지 않고 목록 끝에 보여 주어,
 * HR이 넷 중 하나로 바꿀 때까지 그대로 둔다
 */
function EmploymentTypeSelect({
  value,
  disabled,
  changed,
  onChange,
}: {
  value: string
  disabled: boolean
  changed: boolean
  onChange: (value: string) => void
}) {
  const options: string[] = [...EMPLOYMENT_TYPES]
  if (value && !options.includes(value)) options.push(value)
  return (
    <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger
        size="sm"
        aria-label="고용 형태"
        className={cn(
          'h-7 gap-1 border-0 bg-muted px-2 text-xs focus-visible:ring-1',
          changed && 'bg-pass',
        )}
      >
        <SelectValue placeholder="고용 형태" />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option} value={option} className="text-xs">
            {option}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/**
 * 경력은 신입 · 경력 · 경력 무관 중에서 고르고, 경력이면 "N년 이상" 연차와 직급을 적을 수 있다(연차를 비우면 "경력").
 * 직급은 경력직에서만 뜻이 있어 경력일 때 보인다. 다른 경력이어도 적어 둔 직급이 있으면 지우지 않고 보여 준다.
 * 예전에 글로 적은 경력은 지우지 않고 목록 끝에 보여 준다
 */
function CareerField({
  value,
  position,
  disabled,
  changed,
  onChange,
  onPositionChange,
}: {
  value: string
  position: string
  disabled: boolean
  changed: boolean
  onChange: (value: string) => void
  onPositionChange: (value: string) => void
}) {
  const { kind, years } = parseCareer(value)
  const options: string[] = [...CAREER_KINDS]
  if (value && !kind) options.push(value)
  return (
    <div className={cn('flex items-center gap-1 rounded-md', changed && 'bg-pass')}>
      <Select
        value={(kind ?? value) || undefined}
        onValueChange={(next) =>
          onChange(
            CAREER_KINDS.includes(next as CareerKind)
              ? formatCareer(next as CareerKind, years)
              : next,
          )
        }
        disabled={disabled}
      >
        <SelectTrigger
          size="sm"
          aria-label="경력 구분"
          className={cn(
            'h-7 gap-1 border-0 bg-muted px-2 text-xs focus-visible:ring-1',
            changed && 'bg-pass',
          )}
        >
          <SelectValue placeholder="경력 구분" />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option} value={option} className="text-xs">
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {kind === '경력' && (
        <label className="flex items-center gap-1 text-xs">
          <input
            aria-label="경력 연차"
            type="number"
            min={1}
            max={MAX_CAREER_YEARS}
            value={years ?? ''}
            placeholder="0"
            disabled={disabled}
            onChange={(event) => onChange(formatCareer('경력', toCareerYears(event.target.value)))}
            className="h-7 w-12 rounded-md bg-muted px-2 text-xs outline-none focus:ring-1 focus:ring-ring"
          />
          년 이상
        </label>
      )}
      {(kind === '경력' || position) && (
        <input
          aria-label="직급"
          value={position}
          placeholder="직급 (예: 대리~과장)"
          maxLength={50}
          disabled={disabled}
          onChange={(event) => onPositionChange(event.target.value)}
          style={{ width: `calc(${textWidth(position || '직급 (예: 대리~과장)')}em + 1.25rem)` }}
          className="h-7 rounded-md bg-muted px-2 text-xs outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring"
        />
      )}
    </div>
  )
}

/** 경력을 바꿔 자격 요건 · 우대 사항을 쓰는 기준이 달라졌을 때, 다시 쓸지 묻는 안내 */
function CareerNudge({
  disabled,
  onRewrite,
  onClose,
}: {
  disabled: boolean
  onRewrite: () => void
  onClose: () => void
}) {
  return (
    <div
      role="status"
      className="mb-2 flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-xs"
    >
      <span className="flex-1">
        경력 구분이 바뀌었어요. 자격 요건 · 우대 사항을 바뀐 기준에 맞게 다시 쓸까요?
      </span>
      <Button size="sm" variant="outline" className="h-7" disabled={disabled} onClick={onRewrite}>
        다시 쓰기
      </Button>
      <button
        type="button"
        aria-label="안내 닫기"
        onClick={onClose}
        className="text-muted-foreground hover:text-foreground"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}
