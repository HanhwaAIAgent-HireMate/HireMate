import { useEffect, useState } from 'react'
import { useLocation } from 'react-router'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  useSaveStageGuide,
  useStageGuides,
  type StageGuide,
  type StageGuideView,
} from '@/features/notice/api'
import { errorMessage } from '@/lib/api/client'

/**
 * 안내 칸. 길이는 backend stages 테이블과 같다. 끝나는 시간은 일정에 함께 쓴다.
 * 기타 안내(note)만 선택이고, 나머지가 비어 있으면 게시 · 발송 전에 경고한다.
 * 기타 안내는 메일에 이름 없이 한 줄마다 ※로 붙는다
 */
const FIELDS: {
  key: keyof StageGuide
  label: string
  placeholder: string
  maxLength: number
  optional?: boolean
}[] = [
  { key: 'schedule', label: '일정', placeholder: '예: 11월 3일(화) 오후 2시~4시', maxLength: 200 },
  { key: 'method', label: '진행 방식', placeholder: '예: 대면, 화상, 온라인', maxLength: 100 },
  {
    key: 'place',
    label: '장소·접속 링크',
    placeholder: '예: 서울 중구 OO빌딩 5층 / 링크는 시험 전날 따로 보내 드립니다',
    maxLength: 500,
  },
  { key: 'preparation', label: '준비 사항', placeholder: '예: 신분증, 노트북', maxLength: 1000 },
  {
    key: 'note',
    label: '기타 안내',
    placeholder: '한 줄에 하나씩 써요. 예: 11월 1일까지 참석 여부를 알려 주세요',
    maxLength: 1000,
    optional: true,
  },
]

export const STAGE_GUIDES_ID = 'stage-guides'

// 전형별 안내. 앞 전형의 다음 전형 안내 메일 아래에 붙고, 채용이 끝나기 전까지 고칠 수 있다
export function StageGuides({
  recruitmentId,
  stageIds,
  editable,
}: {
  recruitmentId: string
  /** 전형 ID를 이은 값. 전형 절차가 바뀌면 안내를 새로 받는다 */
  stageIds: string
  editable: boolean
}) {
  const guides = useStageGuides(recruitmentId, stageIds)
  const { hash } = useLocation()

  // 안내 메일 화면의 [입력하러 가기]로 오면 이 칸으로 내려간다
  useEffect(() => {
    if (hash === `#${STAGE_GUIDES_ID}` && guides.data) {
      document.getElementById(STAGE_GUIDES_ID)?.scrollIntoView({ block: 'start' })
    }
  }, [hash, guides.data])

  if (!guides.data?.length) return null
  return (
    <section id={STAGE_GUIDES_ID} className="space-y-3">
      <h2 className="flex flex-wrap items-baseline gap-2 text-sm font-bold">
        전형별 안내
        <span className="text-xs font-normal text-muted-foreground">
          앞 전형의 합격 안내 메일 아래에 붙어요. 비워 둔 칸은 빠져요
        </span>
      </h2>
      {guides.data.map((view) => (
        <GuideCard
          key={`${view.stageId}-${JSON.stringify(view.guide)}`}
          recruitmentId={recruitmentId}
          view={view}
          editable={editable}
        />
      ))}
    </section>
  )
}

function GuideCard({
  recruitmentId,
  view,
  editable,
}: {
  recruitmentId: string
  view: StageGuideView
  editable: boolean
}) {
  const [draft, setDraft] = useState<StageGuide>(view.guide)
  const [confirming, setConfirming] = useState(false)
  const save = useSaveStageGuide(recruitmentId, view.stageId)
  const dirty = FIELDS.some((field) => draft[field.key] !== view.guide[field.key])
  const empty = FIELDS.filter((field) => !field.optional && !draft[field.key].trim())

  const submit = () =>
    save.mutate(draft, {
      onSuccess: () => toast.success(`${view.name} 안내를 저장했어요.`),
      onError: (error) => toast.error(errorMessage(error)),
    })

  return (
    <div className="space-y-2 rounded-xl border p-4">
      <div className="flex items-center gap-2 text-sm font-semibold">
        {view.name}
        {view.notifiedCount > 0 && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-normal text-muted-foreground">
            {view.notifiedCount}명에게 보냄
          </span>
        )}
        {empty.length > 0 && (
          <span className="text-[11px] font-normal text-amber-700">
            비어 있음: {empty.map((field) => field.label).join(', ')}
          </span>
        )}
      </div>
      {FIELDS.map((field) => {
        const props = {
          'aria-label': `${view.name} ${field.label}`,
          value: draft[field.key],
          placeholder: field.placeholder,
          maxLength: field.maxLength,
          disabled: !editable,
          onChange: (event: { target: { value: string } }) =>
            setDraft((current) => ({ ...current, [field.key]: event.target.value })),
        }
        return (
          <label key={field.key} className="grid grid-cols-[96px_1fr] items-start gap-2">
            <span className="pt-1.5 text-xs text-muted-foreground">
              {field.label}
              {field.optional && <span className="ml-1 text-[11px]">(선택)</span>}
            </span>
            {field.optional ? (
              <Textarea {...props} rows={2} className="min-h-0" />
            ) : (
              <Input {...props} />
            )}
          </label>
        )
      })}
      {editable && dirty && (
        <div className="flex justify-end">
          <Button
            size="sm"
            variant="outline"
            disabled={save.isPending}
            onClick={() => (view.notifiedCount > 0 ? setConfirming(true) : submit())}
          >
            안내 저장
          </Button>
        </div>
      )}
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>이미 {view.notifiedCount}명에게 이 안내를 보냈어요</AlertDialogTitle>
            <AlertDialogDescription>
              고친 내용은 이미 보낸 메일에 반영되지 않아요. 안내를 받은 지원자에게는 따로 연락해
              주세요.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction onClick={submit}>저장</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
