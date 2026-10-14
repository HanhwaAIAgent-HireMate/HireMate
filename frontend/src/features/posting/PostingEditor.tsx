import { FileText, Lock, Settings } from 'lucide-react'
import { useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { AiRequestPanel, type AiMessage } from '@/features/posting/AiRequestPanel'
import {
  useApplySuggestion,
  useDiscardSuggestion,
  usePostingAiRequest,
  useSavePosting,
  type Posting,
  type PostingContent,
} from '@/features/posting/api'
import { BulletListField } from '@/features/posting/BulletListField'
import { StageFlow } from '@/features/posting/StageFlow'
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

const LISTS: { key: 'duties' | 'qualifications' | 'preferred' | 'benefits'; label: string }[] = [
  { key: 'duties', label: '주요 업무' },
  { key: 'qualifications', label: '자격 요건' },
  { key: 'preferred', label: '우대 사항' },
]

// PST-01 Job Posting Editor. HR이 직접 쓰거나 AI에게 말해 고치고, 바뀐 부분은 HR이 적용 여부를 정한다
export function PostingEditor({
  posting,
  messages,
  setMessages,
}: {
  posting: Posting
  /** 저장 · 적용으로 편집 상태를 새로 열어도 대화는 남도록 화면이 들고 있다 */
  messages: AiMessage[]
  setMessages: Dispatch<SetStateAction<AiMessage[]>>
}) {
  const navigate = useNavigate()
  const id = posting.recruitmentId
  const [draft, setDraft] = useState<PostingContent>(posting.content)
  const [dirty, setDirty] = useState(false)
  const save = useSavePosting(id)
  const ai = usePostingAiRequest(id)
  const apply = useApplySuggestion(id)
  const discard = useDiscardSuggestion(id)

  const suggestion = posting.suggestion
  const changed = new Set(suggestion?.changedFields ?? [])
  const isDraft = posting.status === 'DRAFT'
  const editable = isDraft || posting.status === 'PUBLISHED'
  const shown = suggestion ? { ...draft, ...pick(suggestion.content, changed) } : draft
  const locked = (field: string) => !editable || changed.has(field)

  const update = (patch: Partial<PostingContent>) => {
    setDraft((current) => ({ ...current, ...patch }))
    setDirty(true)
  }

  const saveDraft = async (silent = false) => {
    if (!dirty) return true
    if (!draft.title.trim()) {
      toast.error('채용명을 입력해 주세요.')
      return false
    }
    try {
      await save.mutateAsync({ ...draft, title: draft.title.trim() })
      setDirty(false)
      if (!silent) toast.success('저장했어요.')
      return true
    } catch (error) {
      toast.error(errorMessage(error))
      return false
    }
  }

  const sendRequest = async (message: string) => {
    setMessages((current) => [...current, { role: 'user', text: message }])
    if (!(await saveDraft(true))) return
    try {
      const answer = await ai.mutateAsync(message)
      setMessages((current) => [
        ...current,
        { role: 'ai', text: answer.reply, agent: answer.agent, stub: answer.stub },
      ])
    } catch (error) {
      setMessages((current) => [...current, { role: 'ai', text: errorMessage(error) }])
    }
  }

  const resolve = (accept: boolean) =>
    (accept ? apply : discard).mutate(undefined, {
      onSuccess: (updated) => {
        setDraft(updated.content)
        setDirty(false)
      },
      onError: (error) => toast.error(errorMessage(error)),
    })

  const goPublish = async () => {
    if (await saveDraft(true)) await navigate(`/hr/recruitments/${id}/posting/publish`)
  }

  const actions = (field: string) =>
    changed.has(field) && (
      <SuggestionActions onApply={() => resolve(true)} onDiscard={() => resolve(false)} />
    )

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b px-6 py-4">
        <h1 className="text-xl font-bold">{isDraft ? '공고 작성' : '공고 수정'}</h1>
        <span className="text-sm text-muted-foreground">기본 Template</span>
        <div className="ml-auto flex gap-2">
          {editable && (
            <Button
              variant="outline"
              onClick={() => void saveDraft()}
              disabled={!dirty || save.isPending}
            >
              {isDraft ? '임시 저장' : '저장'}
            </Button>
          )}
          {isDraft ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button onClick={() => void goPublish()} disabled={Boolean(suggestion)}>
                    승인 및 게시
                  </Button>
                </span>
              </TooltipTrigger>
              {suggestion && (
                <TooltipContent>AI 수정안을 적용하거나 되돌린 뒤 게시해요</TooltipContent>
              )}
            </Tooltip>
          ) : (
            <Button asChild>
              <Link to={`/hr/recruitments/${id}/posting/status`}>접수 현황</Link>
            </Button>
          )}
        </div>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto">
          <div className="mx-auto max-w-[760px] space-y-6 px-6 py-6">
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
                  className="min-w-0 flex-1 bg-transparent outline-none"
                />
                <span className="shrink-0">채용</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {TAGS.map((tag) => (
                  <input
                    key={tag.key}
                    aria-label={tag.placeholder}
                    value={shown[tag.key]}
                    placeholder={tag.placeholder}
                    disabled={locked(tag.key)}
                    onChange={(event) => update({ [tag.key]: event.target.value })}
                    style={{
                      width: `${Math.max(shown[tag.key].length, tag.placeholder.length / 1.6) + 3}ch`,
                    }}
                    className={cn(
                      'h-7 rounded-md bg-muted px-2 text-xs outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring',
                      changed.has(tag.key) && 'bg-pass',
                    )}
                  />
                ))}
              </div>
              {['title', 'jobCategory', 'employmentType', 'career', 'location'].some((field) =>
                changed.has(field),
              ) && actions('title')}
            </div>
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
              <Textarea
                aria-label="회사 소개"
                value={shown.intro}
                disabled={locked('intro')}
                onChange={(event) => update({ intro: event.target.value })}
                className="min-h-0 resize-none border-0 p-0 shadow-none focus-visible:ring-0"
                rows={2}
              />
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
                  onChange={(items) => update({ [list.key]: items })}
                />
                {actions(list.key)}
              </Section>
            ))}
            <FixedBox
              title="전형 절차"
              note={isDraft ? undefined : '게시한 뒤에는 전형 절차를 바꿀 수 없어요'}
            >
              <StageFlow
                stages={suggestion?.stages ?? posting.stages}
                highlight={changed.has('stages')}
              />
              {actions('stages')}
            </FixedBox>
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
                onChange={(items) => update({ benefits: items })}
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
          pending={ai.isPending || save.isPending}
          disabled={!editable}
          onSend={(message) => void sendRequest(message)}
          onReset={() => setMessages([])}
        />
      </div>
    </div>
  )
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

/** 전형 절차 · 필수 제출 서류 · 유의사항처럼 HR 요청으로만 바뀌는 고정 칸 */
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
