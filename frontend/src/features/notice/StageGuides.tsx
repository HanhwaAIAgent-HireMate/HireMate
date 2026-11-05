import { useEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  useSaveStageGuide,
  useStageGuides,
  type StageGuide,
  type StageGuideView,
} from '@/features/notice/api'
import {
  guideProblems,
  METHOD_LABELS,
  missingGuideFields,
  NOTE_MAX,
  nowTime,
  PLACE_MAX,
  PREPARATION_MAX,
  scheduleBounds,
  scheduleRange,
  todayIso,
  type GuideMethod,
  type ScheduleBounds,
} from '@/features/notice/stageGuide'
import { errorMessage } from '@/lib/api/client'

export const NEXT_STAGE_GUIDE_ID = 'next-stage-guide'

/**
 * 전형 결과 화면의 다음 전형 안내 카드. 합격 안내 메일 아래에 붙는다. 결과를 확정한 뒤 메일을 보내기 전에 채우도록
 * 합격 · 불합격 안내 카드 바로 아래에 펼쳐 두고, 안내 메일 화면의 [입력하러 가기](#next-stage-guide)로 오면 이 카드로 내려간다
 */
export function NextStageGuide({
  recruitmentId,
  stageId,
  editable,
}: {
  recruitmentId: string
  /** 다음 전형 ID */
  stageId: string
  editable: boolean
}) {
  const guides = useStageGuides(recruitmentId, stageId)
  const view = guides.data?.find((guide) => guide.stageId === stageId)
  const { hash } = useLocation()
  const linked = hash === `#${NEXT_STAGE_GUIDE_ID}`
  const ready = Boolean(view)

  useEffect(() => {
    if (linked && ready) {
      document.getElementById(NEXT_STAGE_GUIDE_ID)?.scrollIntoView({ block: 'start' })
    }
  }, [linked, ready])

  if (!guides.data || !view) return null
  return (
    <section id={NEXT_STAGE_GUIDE_ID} className="rounded-xl border p-4">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-bold">{view.name} 안내</h2>
        <span className="text-xs text-muted-foreground">합격 안내 메일 아래에 붙어요</span>
      </div>
      <GuideCard
        key={JSON.stringify(view.guide)}
        recruitmentId={recruitmentId}
        view={view}
        bounds={scheduleBounds(guides.data, view.stageId)}
        editable={editable}
      />
    </section>
  )
}

function GuideCard({
  recruitmentId,
  view,
  bounds,
  editable,
}: {
  recruitmentId: string
  view: StageGuideView
  /** 앞 · 뒤 전형의 저장한 일정. 이 전형 일정은 그 사이여야 한다 */
  bounds: ScheduleBounds
  editable: boolean
}) {
  const [draft, setDraft] = useState<StageGuide>(view.guide)
  const save = useSaveStageGuide(recruitmentId, view.stageId)
  // 안내 메일을 받은 지원자가 있으면 잠근다. 시스템에는 지원자가 받은 안내를 그대로 두고, 바뀐 내용은 HR이 연락한다
  const locked = view.notifiedCount > 0
  const canEdit = editable && !locked
  const today = todayIso()
  const dirty = JSON.stringify(draft) !== JSON.stringify(view.guide)
  const now = nowTime()
  const problems = guideProblems(draft, view.guide, bounds, today, now)
  const invalid = Object.keys(problems).length > 0
  const empty = missingGuideFields(draft)
  const range = scheduleRange(bounds, today)
  const keepPast = Boolean(view.guide.schedule && range.min && view.guide.schedule < range.min)
  const change = (patch: Partial<StageGuide>) => setDraft((current) => ({ ...current, ...patch }))

  const submit = () =>
    save.mutate(draft, {
      onSuccess: () => toast.success(`${view.name} 안내를 저장했어요.`),
      onError: (error) => toast.error(errorMessage(error)),
    })

  return (
    <div className="space-y-2">
      {(view.notifiedCount > 0 || empty.length > 0) && (
        <div className="flex items-center gap-2 text-sm">
          {view.notifiedCount > 0 && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
              {view.notifiedCount}명에게 보냄
            </span>
          )}
          {empty.length > 0 && !locked && (
            <span className="text-[11px] text-amber-700">비어 있음: {empty.join(', ')}</span>
          )}
        </div>
      )}
      {locked && (
        <p className="rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
          안내 메일을 보내서 고칠 수 없어요. 바뀐 내용은 받은 지원자에게 전화로 알려 주세요.
        </p>
      )}
      <Field
        label="일정"
        problem={problems.schedule}
        hint={view.type === 'INTERVIEW' ? '면접 시간은 지원자마다 배정돼요' : undefined}
      >
        {/* 면접이 아닌 전형은 공고 게시처럼 날짜와 시작 시각을 한 칸으로 받는다. 면접은 지원자마다 시간을 배정해 날짜만 받는다 */}
        {view.type === 'INTERVIEW' ? (
          <Input
            type="date"
            aria-label={`${view.name} 일정`}
            value={draft.schedule ?? ''}
            // 이미 지난 일정은 그대로 둘 수 있게, 바꾸지 않았으면 지난 날도 범위에 넣는다
            min={keepPast ? undefined : range.min}
            max={range.max}
            disabled={!canEdit}
            onChange={(event) => change({ schedule: event.target.value || null })}
            className="w-44"
          />
        ) : (
          <Input
            type="datetime-local"
            aria-label={`${view.name} 일정`}
            value={draft.schedule ? `${draft.schedule}T${draft.time?.slice(0, 5) ?? '00:00'}` : ''}
            // 오늘부터 고를 수 있으면 지금 시각 이후만 고른다
            min={keepPast ? undefined : `${range.min}T${range.min === today ? now : '00:00'}`}
            max={range.max ? `${range.max}T23:59` : undefined}
            disabled={!canEdit}
            onChange={(event) => {
              const value = event.target.value
              change({
                schedule: value ? value.slice(0, 10) : null,
                time: value ? value.slice(11, 16) : null,
              })
            }}
            className="w-56"
          />
        )}
      </Field>
      <Field label="진행 방식">
        <Select
          value={draft.method ?? ''}
          disabled={!canEdit}
          onValueChange={(method) => change({ method: method as GuideMethod })}
        >
          <SelectTrigger aria-label={`${view.name} 진행 방식`} className="w-44">
            <SelectValue placeholder="골라 주세요" />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(METHOD_LABELS) as GuideMethod[]).map((method) => (
              <SelectItem key={method} value={method}>
                {METHOD_LABELS[method]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field label="장소·접속 링크" problem={problems.place}>
        <Input
          type={draft.method === 'ONLINE' ? 'url' : 'text'}
          aria-label={`${view.name} 장소·접속 링크`}
          value={draft.place}
          placeholder={
            draft.method === 'ONLINE'
              ? 'https://로 시작하는 접속 링크'
              : draft.method === 'OFFLINE'
                ? '예: 서울 중구 OO빌딩 5층'
                : '진행 방식을 먼저 골라 주세요'
          }
          maxLength={PLACE_MAX}
          disabled={!canEdit || (!draft.method && !draft.place)}
          onChange={(event) => change({ place: event.target.value })}
        />
      </Field>
      <Field label="준비 사항" hint={`${draft.preparation.length}/${PREPARATION_MAX}`}>
        <Textarea
          aria-label={`${view.name} 준비 사항`}
          value={draft.preparation}
          placeholder="예: 신분증, 노트북"
          maxLength={PREPARATION_MAX}
          rows={2}
          disabled={!canEdit}
          onChange={(event) => change({ preparation: event.target.value })}
          className="min-h-0"
        />
      </Field>
      <Field label="기타 안내" optional>
        <Textarea
          aria-label={`${view.name} 기타 안내`}
          value={draft.note}
          placeholder="한 줄에 하나씩 써요. 예: 시작 시간은 오후 2시예요"
          maxLength={NOTE_MAX}
          rows={2}
          disabled={!canEdit}
          onChange={(event) => change({ note: event.target.value })}
          className="min-h-0"
        />
      </Field>
      {canEdit && dirty && (
        <div className="flex justify-end">
          <Button size="sm" variant="outline" disabled={save.isPending || invalid} onClick={submit}>
            안내 저장
          </Button>
        </div>
      )}
    </div>
  )
}

/** 칸 이름을 왼쪽에 두고, 맞지 않는 입력이면 칸 아래에 이유를 보여 준다 */
function Field({
  label,
  optional,
  hint,
  problem,
  children,
}: {
  label: string
  optional?: boolean
  hint?: string
  problem?: string
  children: ReactNode
}) {
  return (
    <div className="grid grid-cols-[96px_1fr] items-start gap-2">
      <span className="pt-1.5 text-xs text-muted-foreground">
        {label}
        {optional && <span className="ml-1 text-[11px]">(선택)</span>}
      </span>
      <div className="space-y-1">
        {children}
        {problem && <p className="text-xs text-destructive">{problem}</p>}
        {hint && <p className="text-right text-[11px] text-muted-foreground">{hint}</p>}
      </div>
    </div>
  )
}
