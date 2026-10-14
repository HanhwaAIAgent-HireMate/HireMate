import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { useDecisionActions } from '@/features/screening/api'
import { useStageUi } from '@/features/screening/store'
import { errorMessage } from '@/lib/api/client'

type LastDecision = { ids: string[]; names: string[]; decision: 'PASS' | 'FAIL' }

/**
 * 맨 아래 결정 버튼 (STG-07). 체크한 지원자를 확인 창 없이 한 번에 결정하고, 방금 한 결정은 되돌릴 수 있다.
 */
export function DecisionBar({
  stageId,
  editable,
  names,
}: {
  stageId: string
  editable: boolean
  /** 체크한 지원자 이름 (안내 문구용) */
  names: Record<string, string>
}) {
  const { checked, setChecked } = useStageUi()
  const { decide, revert } = useDecisionActions(stageId)
  const [last, setLast] = useState<LastDecision | null>(null)
  const count = checked.length

  const run = (decision: 'PASS' | 'FAIL') => {
    const ids = [...checked]
    decide.mutate(
      { ids, decision },
      {
        onSuccess: () => {
          setLast({ ids, names: ids.map((id) => names[id] ?? '지원자'), decision })
          setChecked([])
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  const undo = () => {
    if (!last) return
    revert.mutate(last.ids, {
      onSuccess: () => setLast(null),
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
          <button
            onClick={undo}
            disabled={revert.isPending}
            className="font-semibold text-ai-soft hover:underline"
          >
            되돌리기
          </button>
        </div>
      )}
      <div className="flex items-center gap-2 border-t px-4 py-3">
        <span className="flex-1 text-sm text-muted-foreground">{count}명 선택됨</span>
        <Button
          variant="outline"
          disabled={!editable || count === 0 || decide.isPending}
          onClick={() => run('FAIL')}
          className="border-fail-foreground/40 text-fail-foreground hover:bg-fail disabled:border-border disabled:text-muted-foreground"
        >
          <X />
          불합격
        </Button>
        <Button
          disabled={!editable || count === 0 || decide.isPending}
          onClick={() => run('PASS')}
          className="bg-pass-foreground text-white hover:bg-pass-foreground/90 disabled:border-border disabled:bg-background disabled:text-muted-foreground"
        >
          <Check />
          합격
        </Button>
      </div>
    </div>
  )
}
