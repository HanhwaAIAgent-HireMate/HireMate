import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { RegisterDialog } from '@/features/assessment/RegisterDialog'
import { InterviewAssign } from '@/features/interview/InterviewAssign'
import { useConfirmStage, type StageOverview } from '@/features/screening/api'
import { errorMessage } from '@/lib/api/client'
import { withRo } from '@/lib/format'

/** Stage 바 (COM-01): [면접관 배정](면접 전형) · 결정 현황 · [전형 결과 확정]. 전형 단계 줄 오른쪽에 들어간다 */
export function StageBar({ overview }: { overview: StageOverview }) {
  const [confirming, setConfirming] = useState(false)
  const [registering, setRegistering] = useState(false)
  // 평가 전형은 결과가 없으면 [평가 결과 등록]으로 시작한다 (STG-10)
  const assessment = overview.type === 'ASSESSMENT'
  const { counts } = overview
  const closePath = `/hr/recruitments/${overview.recruitmentId}/stages/${overview.stageId}/close`

  return (
    <>
      {/* 전형을 옮기면 열려 있던 설정 창과 고르던 값을 비우도록 전형마다 새로 만든다 */}
      {overview.type === 'INTERVIEW' && (
        <InterviewAssign
          key={overview.stageId}
          stageId={overview.stageId}
          editable={overview.status === 'PENDING' || overview.status === 'ACTIVE'}
        />
      )}
      <Count color="bg-muted-foreground/40" label="미결정" value={counts.pending} />
      <Count color="bg-pass-foreground" label="합격" value={counts.pass} />
      <Count color="bg-fail-foreground" label="불합격" value={counts.fail} />
      {overview.status === 'ACTIVE' && assessment && (
        <Button
          variant={overview.hasScores ? 'outline' : 'default'}
          onClick={() => setRegistering(true)}
        >
          평가 결과 등록
        </Button>
      )}
      {overview.status === 'ACTIVE' && (!assessment || overview.hasScores) && (
        <Button onClick={() => setConfirming(true)}>전형 결과 확정</Button>
      )}
      {overview.status === 'CONFIRMED' && (
        <Button asChild>
          <Link to={closePath}>안내 · 전형 종료</Link>
        </Button>
      )}
      {overview.status === 'DONE' && (
        <span className="text-sm text-muted-foreground">종료된 전형</span>
      )}
      <ConfirmDialog
        overview={overview}
        open={confirming}
        onOpenChange={setConfirming}
        closePath={closePath}
      />
      {assessment && (
        <RegisterDialog overview={overview} open={registering} onOpenChange={setRegistering} />
      )}
    </>
  )
}

function Count({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground">
      <span className={`size-1.5 rounded-full ${color}`} />
      {label}
      <span className="font-bold text-foreground">{value}</span>
    </span>
  )
}

/** STG-08 전형 결과 확정. 합격자만 다음 전형으로 넘어가고 미결정은 불합격으로 확정된다. */
function ConfirmDialog({
  overview,
  open,
  onOpenChange,
  closePath,
}: {
  overview: StageOverview
  open: boolean
  onOpenChange: (open: boolean) => void
  closePath: string
}) {
  const navigate = useNavigate()
  const confirm = useConfirmStage(overview.stageId)
  const { pass, fail, pending } = overview.counts
  const index = overview.steps.findIndex((step) => step.stageId === overview.stageId)
  const next = overview.steps[index + 1]

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{overview.name} 결과를 확정할까요?</AlertDialogTitle>
        </AlertDialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-pass p-4">
            <div className="text-xs font-semibold text-pass-foreground">합격</div>
            <div className="mt-1 text-2xl font-bold">
              {pass} <span className="text-sm font-normal text-muted-foreground">명</span>
            </div>
          </div>
          <div className="rounded-xl bg-fail p-4">
            <div className="text-xs font-semibold text-fail-foreground">불합격</div>
            <div className="mt-1 text-2xl font-bold">
              {fail + pending} <span className="text-sm font-normal text-muted-foreground">명</span>
            </div>
            {pending > 0 && (
              <div className="mt-0.5 text-xs text-muted-foreground">미결정 {pending}명 포함</div>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          {next
            ? `합격 ${pass}명은 ${withRo(next.name)} 넘어가요.`
            : `마지막 전형이라 합격 ${pass}명이 최종 합격이에요.`}
        </p>
        {next?.type === 'INTERVIEW' && pass > 0 && (
          <p className="text-sm text-muted-foreground">
            확정하면 합격자 {pass}명의 {next.name} 질문과 면접 일정을 백그라운드에서 준비해요.
            일정은 다음 전형 안내의 날짜부터 평일 09~18시에 1시간씩 배정하고, 다음 전형 전까지
            시간이 부족하면 같은 시간에 여러 명을 배정해요. 다음 전형은 안내 발송 후 별도로
            시작해요.
          </p>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>취소</AlertDialogCancel>
          <Button
            disabled={confirm.isPending}
            onClick={() =>
              confirm.mutate(undefined, {
                onSuccess: () => {
                  onOpenChange(false)
                  void navigate(closePath)
                },
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
          >
            확정
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
