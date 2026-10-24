import type { StageOverview } from '@/features/screening/api'
import { WorkflowStepper, type StepItem } from '@/features/recruit/WorkflowStepper'

/** 공고에서 정한 전형 순서와 대상 인원. 누르면 그 전형으로 간다. */
export function StageStepper({ overview }: { overview: StageOverview }) {
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
  return <WorkflowStepper items={items} />
}
