import type { ReactNode } from 'react'

import type { StageOverview } from '@/features/screening/api'
import { WorkflowStepper, type StepItem } from '@/features/recruit/WorkflowStepper'

/** 공고에서 정한 전형 순서와 대상 인원. 누르면 그 전형으로 간다. actions는 같은 줄 오른쪽에 둔다. */
export function StageStepper({
  overview,
  actions,
}: {
  overview: StageOverview
  actions?: ReactNode
}) {
  const base = `/hr/recruitments/${overview.recruitmentId}`
  const items: StepItem[] = [
    {
      key: 'posting',
      label: '공고',
      count: overview.applicantCount,
      state: 'done',
      to: `${base}/posting/status`,
    },
    ...overview.steps.map((step) => ({
      key: step.stageId,
      label: step.name,
      type: step.type,
      icon: step.icon,
      count: step.targetCount,
      state:
        step.stageId === overview.stageId
          ? ('active' as const)
          : step.status === 'DONE'
            ? ('done' as const)
            : step.status === 'PENDING'
              ? ('pending' as const)
              : ('ongoing' as const),
      to: `${base}/stages/${step.stageId}`,
    })),
  ]
  return <WorkflowStepper items={items} actions={actions} />
}
