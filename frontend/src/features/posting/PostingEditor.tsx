import { ArrowRight, FileText, Lock, Settings } from 'lucide-react'
import { useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { Link, useNavigate } from 'react-router'
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
import { StageGuides } from '@/features/notice/StageGuides'
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
import { usePostingRecovery } from '@/features/posting/usePostingRecovery'
import { stagesProblem, toStageForms, type StageForm } from '@/features/posting/stages'
import {
  CONDITION_FIELDS,
  CAREER_KINDS,
  CONDITION_KEYS,
  EMPLOYMENT_TYPES,
  MAX_CAREER_YEARS,
  formatCareer,
  parseCareer,
  toCareerYears,
  type CareerKind,
  MAX_HEADCOUNT,
  toHeadcount,
} from '@/features/posting/conditions'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const EXAMPLES = [
  '우대 사항에 결제·정산 경험을 더 구체적으로 써줘',
  '전형은 서류, 직무역량 평가, 개발 과제, 1차 실무면접, 최종면접 순으로 해줘',
  '포트폴리오도 필수로 받아줘',
]

const TAGS: {
  key: 'jobCategory' | 'employmentType' | 'career' | 'location'
  placeholder: string
}[] = [
  { key: 'jobCategory', placeholder: '직무 (예: 개발 › 백엔드)' },
  { key: 'employmentType', placeholder: '고용 형태' },
  { key: 'career', placeholder: '경력' },
  { key: 'location', placeholder: '근무지' },
]

type ListKey = 'duties' | 'qualifications' | 'preferred' | 'benefits'

const LISTS: { key: ListKey; label: string }[] = [
  { key: 'duties', label: '주요 업무' },
  { key: 'qualifications', label: '자격 요건' },
  { key: 'preferred', label: '우대 사항' },
]

/** 수정안을 한 덩어리로 처리하는 기본 정보 칸 */
const BASIC_FIELDS = ['title', 'jobCategory', 'employmentType', 'career', 'location']

// PST-01 Job Posting Editor. HR이 직접 쓰거나 AI에게 말해 고치고, 바뀐 부분은 HR이 적용 여부를 정한다
export function PostingEditor({
  posting,
  messages,
  setMessages,
  focus,
  setFocus,
}: {
  posting: Posting
  /** 저장 · 적용으로 편집 상태를 새로 열어도 대화와 고른 줄은 남도록 화면이 들고 있다 */
  messages: AiMessage[]
  setMessages: Dispatch<SetStateAction<AiMessage[]>>
  focus: LineFocus | null
  setFocus: Dispatch<SetStateAction<LineFocus | null>>
}) {
  const navigate = useNavigate()
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
  const [stagesError, setStagesError] = useState<string | null>(null)
  const save = useSavePosting(id)
  const saveStages = useSaveStages(id)
  const ai = usePostingAiRequest(id)
  const apply = useApplySuggestion(id)
  const discard = useDiscardSuggestion(id)
  const saving = save.isPending || saveStages.isPending

  const suggestion = posting.suggestion
  const changed = new Set(suggestion?.changedFields ?? [])
  const isDraft = posting.status === 'DRAFT'
  // 게시한 공고는 모든 지원자가 같은 공고를 보도록 바꿀 수 없다. 전형별 안내(일정 · 장소)만 고칠 수 있다
  const editable = isDraft
  const shown = suggestion ? { ...draft, ...pick(suggestion.content, changed) } : draft
  const locked = (field: string) => !editable || changed.has(field)
  // 고른 줄. 그 칸에 수정안이 생겨 잠기거나 줄이 비면 고르지 않은 것으로 본다
  const picked = focus && !locked(focus.field) && hasLine(focus, draft) ? focus : null

  const update = (patch: Partial<PostingContent>) => {
    setDraft((current) => ({ ...current, ...patch }))
  }

  /** 줄 앞의 ·을 누르면 그 줄을 고르고, 고른 줄을 다시 누르면 푼다 */
  const toggleFocus = (next: LineFocus) =>
    setFocus(picked?.field === next.field && picked.index === next.index ? null : next)

  /** 고른 칸에서 줄을 더하거나 지우면 줄 순서가 바뀌어 고르기를 푼다 */
  const changeList = (key: ListKey, items: string[]) => {
    if (focus?.field === key && items.length !== draft[key].length) setFocus(null)
    update({ [key]: items })
  }

  const changeStages = (next: StageForm[]) => {
    setStages(next)
    setStagesError(null)
  }

  const saveDraft = async (silent = false) => {
    if (!dirty && !stagesDirty) return true
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
      if (dirty) {
        await save.mutateAsync({ ...draft, title: draft.title.trim() })
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
        if (accept && targets.has('stages')) {
          setStages(toStageForms(updated.stages))
        }
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const goPublish = async () => {
    if (await saveDraft(true)) await navigate(`/hr/recruitments/${id}/posting/poster`)
  }

  /**
   * 덩어리마다 [적용] [되돌리기]. 기본 정보(채용명 · 직무 · 고용 형태 · 경력 · 근무지)와
   * 모집 조건(채용 인원 · 직급 · 학력 · 급여 · 근무 일시)은 각각 한 덩어리로 처리한다
   */
  const actions = (field: string) => {
    let fields = BASIC_FIELDS.includes(field)
      ? BASIC_FIELDS
      : CONDITION_KEYS.includes(field)
        ? CONDITION_KEYS
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
      <PostingStepHeader title={isDraft ? '공고 작성' : '게시한 공고'} caption="기본 Template">
        {editable && (
          <Button
            variant="outline"
            className="min-w-20"
            onClick={() => void saveDraft()}
            disabled={!(dirty || stagesDirty) || saving}
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
                  disabled={Boolean(suggestion)}
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
      {editable && (dirty || stagesDirty) && (
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
                게시한 공고는 바꿀 수 없어요. 전형 일정 · 장소는 아래 전형별 안내에서 고칠 수
                있어요.
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
                <span className="shrink-0">채용</span>
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
                      disabled={locked(tag.key)}
                      changed={changed.has(tag.key)}
                      onChange={(career) => update({ career })}
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
              </div>
              {actions('title')}
            </div>
            <Section title="모집 조건">
              <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                {CONDITION_FIELDS.map((field) => (
                  <label
                    key={field.key}
                    className={cn('flex items-center gap-2 text-sm', field.wide && 'col-span-2')}
                  >
                    <span className="w-16 shrink-0 text-xs text-muted-foreground">
                      {field.label}
                    </span>
                    <input
                      aria-label={field.label}
                      type={field.key === 'headcount' ? 'number' : 'text'}
                      min={field.key === 'headcount' ? 1 : undefined}
                      max={field.key === 'headcount' ? MAX_HEADCOUNT : undefined}
                      value={field.key === 'headcount' ? (shown.headcount ?? '') : shown[field.key]}
                      placeholder={field.placeholder}
                      maxLength={field.maxLength}
                      disabled={locked(field.key)}
                      onChange={(event) =>
                        update({
                          [field.key]:
                            field.key === 'headcount'
                              ? toHeadcount(event.target.value)
                              : event.target.value,
                        })
                      }
                      className={cn(
                        'h-8 min-w-0 flex-1 rounded-md bg-muted px-2 outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring',
                        field.key === 'headcount' && 'max-w-24 flex-none',
                        changed.has(field.key) && 'bg-pass',
                      )}
                    />
                    {field.key === 'headcount' && <span className="text-xs">명</span>}
                  </label>
                ))}
              </div>
              {actions('headcount')}
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
            <StageGuides
              recruitmentId={id}
              stageIds={posting.stages.map((stage) => stage.id).join()}
              editable={posting.status !== 'CLOSED'}
            />
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
 * 경력은 신입 · 경력 · 경력 무관 중에서 고르고, 경력이면 "N년 이상" 연차를 적을 수 있다(비우면 "경력").
 * 예전에 글로 적은 값은 지우지 않고 목록 끝에 보여 준다
 */
function CareerField({
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
          aria-label="경력"
          className={cn(
            'h-7 gap-1 border-0 bg-muted px-2 text-xs focus-visible:ring-1',
            changed && 'bg-pass',
          )}
        >
          <SelectValue placeholder="경력" />
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
    </div>
  )
}
