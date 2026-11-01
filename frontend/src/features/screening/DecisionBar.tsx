import { Check, Undo2, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { missingOpinions, useStageOpinions } from '@/features/interview/opinions'
import {
  useCandidateDetail,
  useDecisionActions,
  useStageOverview,
  type Decision,
} from '@/features/screening/api'
import { useStageUi } from '@/features/screening/store'
import { errorMessage } from '@/lib/api/client'

type LastDecision = { ids: string[]; names: string[]; decision: 'PASS' | 'FAIL' }

/**
 * 맨 아래 결정 버튼 (STG-07). 체크한 지원자를 확인 창 없이 한 번에 결정한다. 체크한 지원자가 없고 지원자 카드를 열어
 * 두었으면 그 지원자를 결정한다. 열어 둔 지원자가 결정된 상태면 합격 · 불합격은 꺼지고 되돌리기만 켜진다.
 * 서버가 결정을 받으면 다시 불러오기를 기다리지 않고 바로 버튼 상태를 바꾼다.
 */
export function DecisionBar({
  stageId,
  tabId,
  editable,
  names,
}: {
  stageId: string
  /** 되돌리기를 누른 탭. 그 탭에 없던 지원자는 되돌리면 그 탭에 들어온다 */
  tabId: string
  editable: boolean
  /** 체크한 지원자 이름 (안내 문구용) */
  names: Record<string, string>
}) {
  const { checked, setChecked, openId } = useStageUi()
  const { decide, revert } = useDecisionActions(stageId, tabId)
  const [last, setLast] = useState<LastDecision | null>(null)
  // 서버가 받은 결정을 다시 불러오기 전에 먼저 반영한다. 그때의 서버 값(before)이 바뀌면 다시 불러온 서버 값을 따른다
  const [known, setKnown] = useState<
    Record<string, { decision: Decision; before: Decision | undefined }>
  >({})
  const open = useCandidateDetail(stageId, openId ?? '')
  // 면접 전형: 배정된 면접관의 의견이 빠진 지원자를 결정하면 한 번 확인한다 (막지는 않는다. 결정은 HR이 한다)
  const overview = useStageOverview(stageId)
  const interview = overview.data?.type === 'INTERVIEW'
  const opinions = useStageOpinions(stageId, interview)
  const [warning, setWarning] = useState<{ decision: 'PASS' | 'FAIL'; lines: string[] } | null>(
    null,
  )
  const openRow = openId ? open.data?.row : undefined

  const single = checked.length === 0 ? openRow : undefined
  const pending = single ? known[single.applicationId] : undefined
  const singleDecision =
    single && pending && pending.before === single.decision ? pending.decision : single?.decision
  const targets = checked.length > 0 ? checked : single ? [single.applicationId] : []
  const targetNames =
    checked.length > 0 ? names : single ? { [single.applicationId]: single.name } : {}
  const busy = decide.isPending || revert.isPending

  const canDecide =
    editable &&
    !busy &&
    targets.length > 0 &&
    (single === undefined || singleDecision === 'PENDING')
  const canRevert =
    editable &&
    !busy &&
    (single !== undefined ? singleDecision !== 'PENDING' : checked.length === 0 && last !== null)

  const label =
    checked.length > 0
      ? `${checked.length}명 선택됨`
      : single
        ? `${single.name} 님${singleDecision === 'PASS' ? ' · 합격' : singleDecision === 'FAIL' ? ' · 불합격' : ''}`
        : '0명 선택됨'

  const remember = (ids: string[], decision: Decision) => {
    const before =
      ids.length === 1 && single?.applicationId === ids[0] ? single.decision : undefined
    setKnown((current) => ({
      ...current,
      ...Object.fromEntries(ids.map((id) => [id, { decision, before }])),
    }))
  }

  const run = (decision: 'PASS' | 'FAIL') => {
    const ids = [...targets]
    decide.mutate(
      { ids, decision },
      {
        onSuccess: () => {
          remember(ids, decision)
          setLast({ ids, names: ids.map((id) => targetNames[id] ?? '지원자'), decision })
          setChecked([])
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  const attempt = (decision: 'PASS' | 'FAIL') => {
    const lines = interview
      ? targets.flatMap((id) => {
          const missing = missingOpinions(opinions.data?.find((row) => row.applicationId === id))
          return missing.length
            ? [`${targetNames[id] ?? '지원자'}: ${missing.join(' · ')} 의견이 아직 없어요`]
            : []
        })
      : []
    if (lines.length) setWarning({ decision, lines })
    else run(decision)
  }

  const undo = () => {
    const ids = single ? [single.applicationId] : (last?.ids ?? [])
    if (ids.length === 0) return
    revert.mutate(ids, {
      onSuccess: () => {
        remember(ids, 'PENDING')
        setLast(null)
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const who =
    last && (last.names.length === 1 ? `${last.names[0]} 님을` : `${last.names.length}명을`)

  return (
    <div className="relative shrink-0">
      {last && (
        <div className="absolute inset-x-3 bottom-full mb-2 flex items-center gap-3 rounded-lg bg-foreground px-3 py-2.5 text-sm text-background shadow-lg">
          <button
            aria-label="알림 닫기"
            onClick={() => setLast(null)}
            className="opacity-70 hover:opacity-100"
          >
            <X className="size-4" />
          </button>
          <span className="flex-1">
            {who} {last.decision === 'PASS' ? '합격' : '불합격'} 처리했어요
          </span>
        </div>
      )}
      <div className="flex items-center gap-2 border-t px-4 py-3">
        <span className="flex-1 truncate text-sm text-muted-foreground">{label}</span>
        <Button variant="outline" disabled={!canRevert} onClick={undo}>
          <Undo2 />
          되돌리기
        </Button>
        <Button
          variant="outline"
          disabled={!canDecide}
          onClick={() => attempt('FAIL')}
          className="border-fail-foreground/40 text-fail-foreground hover:bg-fail disabled:border-border disabled:text-muted-foreground"
        >
          <X />
          불합격
        </Button>
        <Button
          disabled={!canDecide}
          onClick={() => attempt('PASS')}
          className="bg-pass-foreground text-white hover:bg-pass-foreground/90 disabled:border-border disabled:bg-background disabled:text-muted-foreground"
        >
          <Check />
          합격
        </Button>
      </div>
      <AlertDialog open={warning !== null} onOpenChange={(value) => !value && setWarning(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>면접관 의견이 아직 없는 지원자가 있어요</AlertDialogTitle>
            <AlertDialogDescription>
              그래도 결정할까요? 결정은 채용 담당자가 해요.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="space-y-1 text-sm">
            {warning?.lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <Button
              onClick={() => {
                if (warning) run(warning.decision)
                setWarning(null)
              }}
            >
              그래도 {warning?.decision === 'FAIL' ? '불합격' : '합격'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
