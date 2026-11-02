import { type ReactNode } from 'react'

import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { type StageGuide, type StageGuideView } from '@/features/notice/api'
import {
  METHOD_LABELS,
  missingGuideFields,
  NOTE_MAX,
  PLACE_MAX,
  PREPARATION_MAX,
  scheduleRange,
  todayIso,
  type GuideMethod,
  type GuideProblems,
  type ScheduleBounds,
} from '@/features/notice/stageGuide'

/**
 * 다음 전형 안내 메일 화면에서 고치는 다음 전형의 안내. 메일 본문 아래에 붙고, 비워 둔 칸은 빠진다.
 * 일정이 자주 바뀌어 공고 작성이 아니라 메일을 보내기 전에 채운다. 메일을 보내면 함께 잠긴다
 */
export function StageGuideFields({
  view,
  draft,
  bounds,
  problems,
  disabled,
  onChange,
}: {
  view: StageGuideView
  draft: StageGuide
  /** 앞 · 뒤 전형의 저장한 일정. 이 전형 일정은 그 사이여야 한다 */
  bounds: ScheduleBounds
  problems: GuideProblems
  disabled: boolean
  onChange: (patch: Partial<StageGuide>) => void
}) {
  const range = scheduleRange(bounds, todayIso())
  const empty = missingGuideFields(draft)
  return (
    <div className="space-y-2">
      {empty.length > 0 && (
        <p className="text-[11px] text-amber-700">비어 있음: {empty.join(', ')}</p>
      )}
      <Field label="일정" problem={problems.schedule}>
        <Input
          type="date"
          aria-label={`${view.name} 일정`}
          value={draft.schedule ?? ''}
          // 이미 지난 일정은 그대로 둘 수 있게, 바꾸지 않았으면 지난 날도 범위에 넣는다
          min={view.guide.schedule && view.guide.schedule < range.min ? undefined : range.min}
          max={range.max}
          disabled={disabled}
          onChange={(event) => onChange({ schedule: event.target.value || null })}
          className="w-44 bg-background"
        />
      </Field>
      <Field label="진행 방식">
        <Select
          value={draft.method ?? ''}
          disabled={disabled}
          onValueChange={(method) => onChange({ method: method as GuideMethod })}
        >
          <SelectTrigger aria-label={`${view.name} 진행 방식`} className="w-44 bg-background">
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
          disabled={disabled || (!draft.method && !draft.place)}
          onChange={(event) => onChange({ place: event.target.value })}
          className="bg-background"
        />
      </Field>
      <Field label="준비 사항" hint={`${draft.preparation.length}/${PREPARATION_MAX}`}>
        <Textarea
          aria-label={`${view.name} 준비 사항`}
          value={draft.preparation}
          placeholder="예: 신분증, 노트북"
          maxLength={PREPARATION_MAX}
          rows={2}
          disabled={disabled}
          onChange={(event) => onChange({ preparation: event.target.value })}
          className="min-h-0 bg-background"
        />
      </Field>
      <Field label="기타 안내" optional>
        <Textarea
          aria-label={`${view.name} 기타 안내`}
          value={draft.note}
          placeholder="한 줄에 하나씩 써요. 예: 시작 시간은 오후 2시예요"
          maxLength={NOTE_MAX}
          rows={2}
          disabled={disabled}
          onChange={(event) => onChange({ note: event.target.value })}
          className="min-h-0 bg-background"
        />
      </Field>
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
