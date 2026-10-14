import { useEffect } from 'react'
import { useParams } from 'react-router'

import { useHeaderCrumb } from '@/app/header-store'
import { Skeleton } from '@/components/ui/skeleton'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { careersPath, RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import { useSelection, useStageOverview } from '@/features/screening/api'
import { CandidateCard } from '@/features/screening/CandidateCard'
import { CandidateList } from '@/features/screening/CandidateList'
import { DecisionBar } from '@/features/screening/DecisionBar'
import { SelectionPanel } from '@/features/screening/SelectionPanel'
import { StageBar } from '@/features/screening/StageBar'
import { StageStepper } from '@/features/screening/StageHeader'
import { useStageUi } from '@/features/screening/store'

// Generic Stage Page (STG-01). 서류 · 평가 · 면접 전형이 모두 같은 3단 구조를 쓰고, 지원자 카드의 Viewer만 바뀐다
export function StagePage() {
  const { stageId = '' } = useParams()
  const overview = useStageOverview(stageId)
  const selection = useSelection(stageId)
  const { openId, reset } = useStageUi()

  useEffect(() => reset(stageId), [reset, stageId])
  useHeaderCrumb(
    overview.data && {
      title: overview.data.recruitmentTitle,
      status: RECRUITMENT_STATUS_LABELS[overview.data.recruitmentStatus],
      careersPath: careersPath(overview.data.postingId),
    },
  )

  if (!overview.data) {
    return (
      <div className="space-y-3 p-6">
        <h1 className="sr-only">공통 전형 화면</h1>
        {overview.isError ? (
          <p className="text-sm text-muted-foreground">전형을 찾지 못했어요.</p>
        ) : (
          <Skeleton className="h-96 w-full" />
        )}
      </div>
    )
  }

  const data = overview.data
  const editable = data.status === 'ACTIVE'
  const names = Object.fromEntries(
    (selection.data?.items ?? []).map((row) => [row.applicationId, row.name]),
  )

  return (
    <div className="flex h-full flex-col">
      <StageStepper overview={data} />
      <StageBar overview={data} />
      <div className="flex min-h-0 flex-1">
        <CandidateList overview={data} editable={editable} />
        <section className="flex min-w-0 flex-1 flex-col">
          {openId ? (
            <CandidateCard
              key={openId}
              overview={data}
              applicationId={openId}
              editable={editable}
              selectedCount={data.selectedCount}
            />
          ) : (
            <SelectionPanel overview={data} editable={editable} />
          )}
          <DecisionBar stageId={data.stageId} editable={editable} names={names} />
        </section>
        <ChatPanel />
      </div>
    </div>
  )
}
