import { UsersRound } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useInterviewerAccounts } from '@/features/company/api'
import {
  useAssignInterviewers,
  useStageInterviewers,
  type InterviewerSlot,
} from '@/features/interview/assignments'
import { RoleTag, type InterviewerRole } from '@/features/interview/RoleTag'
import type { StageOverview } from '@/features/screening/api'
import { errorMessage } from '@/lib/api/client'
import { useMe } from '@/lib/auth'

const ROLES: { role: InterviewerRole; label: string }[] = [
  { role: 'HR', label: '인사' },
  { role: 'PRACTICAL', label: '실무' },
]

/** 지금 화면은 담당마다 한 명을 고른다. 담당별 인원 · 종류는 팀 논의 뒤 정한다 (서버는 행 단위로 저장한다) */
function pick(slots: InterviewerSlot[] | undefined): Record<InterviewerRole, string> {
  const find = (role: InterviewerRole) => slots?.find((slot) => slot.role === role)?.memberId ?? ''
  return { HR: find('HR'), PRACTICAL: find('PRACTICAL') }
}

/** 면접 전형 위쪽의 [면접관]: 인사 · 실무 면접관 계정을 지정한다. 지정된 계정만 면접관 모드로 이 전형을 연다 */
export function InterviewerAssign({ overview }: { overview: StageOverview }) {
  const [open, setOpen] = useState(false)
  const interviewers = useStageInterviewers(overview.stageId)
  const accounts = useInterviewerAccounts()
  const me = useMe()
  const assign = useAssignInterviewers(overview.stageId)
  const [draft, setDraft] = useState<Record<InterviewerRole, string>>({ HR: '', PRACTICAL: '' })
  const editable = overview.status === 'PENDING' || overview.status === 'ACTIVE'
  const slots = interviewers.data?.slots ?? []
  // HR 본인도 면접관으로 지정할 수 있다 (인사 면접을 HR이 직접 보는 경우)
  const options = [
    ...(me.data ? [{ memberId: me.data.memberId, name: `${me.data.name} (나)` }] : []),
    ...(accounts.data ?? []).map((account) => ({ memberId: account.memberId, name: account.name })),
  ]
  const summary = slots.length
    ? ROLES.flatMap(({ role, label }) =>
        slots.filter((slot) => slot.role === role).map((slot) => `${label} ${slot.name}`),
      ).join(' · ')
    : '면접관 지정'

  return (
    <Popover
      open={open}
      onOpenChange={(value) => {
        if (value) setDraft(pick(slots))
        setOpen(value)
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">
          <UsersRound />
          {summary}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-3">
        <div>
          <p className="text-sm font-semibold">면접관 지정</p>
          <p className="text-xs text-muted-foreground">
            지정된 계정만 면접관 모드로 이 전형을 열고, 자기 담당 질문에 답변을 기록해요.
          </p>
        </div>
        {ROLES.map(({ role, label }) => (
          <label key={role} className="block space-y-1.5">
            <RoleTag role={role} questionText={`${label} 면접관`} />
            <select
              aria-label={`${label} 면접관`}
              value={draft[role]}
              disabled={!editable}
              onChange={(event) => setDraft({ ...draft, [role]: event.target.value })}
              className="h-9 w-full rounded-md border bg-background px-2 text-sm"
            >
              <option value="">지정 안 함</option>
              {options.map((option) => (
                <option key={option.memberId} value={option.memberId}>
                  {option.name}
                </option>
              ))}
            </select>
          </label>
        ))}
        <p className="text-xs text-muted-foreground">
          면접관 계정은{' '}
          <Link to="/hr/settings/interviewers" className="underline underline-offset-4">
            설정 › 면접관
          </Link>
          에서 만들어요.
        </p>
        {editable ? (
          <Button
            size="sm"
            className="w-full"
            disabled={assign.isPending}
            onClick={() =>
              assign.mutate(
                ROLES.filter(({ role }) => draft[role]).map(({ role }) => ({
                  role,
                  memberId: draft[role],
                })),
                {
                  onSuccess: () => {
                    toast.success('면접관을 지정했어요.')
                    setOpen(false)
                  },
                  onError: (error) => toast.error(errorMessage(error)),
                },
              )
            }
          >
            저장
          </Button>
        ) : (
          <p className="text-xs text-muted-foreground">결과를 확정한 전형은 바꿀 수 없어요.</p>
        )}
      </PopoverContent>
    </Popover>
  )
}
