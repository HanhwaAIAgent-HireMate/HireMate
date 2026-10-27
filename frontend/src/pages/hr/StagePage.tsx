import { useEffect } from 'react'
import { type LayoutStorage, useDefaultLayout } from 'react-resizable-panels'
import { useParams } from 'react-router'

import { useHeaderCrumb } from '@/app/header-store'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
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

// 담당자가 조절한 칸 너비를 브라우저에 남긴다. 저장소를 쓸 수 없거나 값이 깨졌으면 기본 너비로 연다
const layoutStorage: LayoutStorage = {
  getItem: (key) => {
    try {
      const value = localStorage.getItem(key)
      return value !== null && JSON.parse(value) ? value : null
    } catch {
      return null
    }
  },
  setItem: (key, value) => {
    try {
      localStorage.setItem(key, value)
    } catch {
      // 저장하지 못해도 지금 화면의 너비는 그대로 쓴다
    }
  },
}

// Generic Stage Page (STG-01). 서류 · 평가 · 면접 전형이 모두 같은 3단 구조를 쓰고, 지원자 카드의 Viewer만 바뀐다
export function StagePage() {
  const { stageId = '' } = useParams()
  const overview = useStageOverview(stageId)
  const selection = useSelection(stageId)
  const { openId, reset, syncSelection } = useStageUi()
  const layout = useDefaultLayout({ id: 'stage-panels', storage: layoutStorage })
  const selectedRows = selection.data?.items

  useEffect(() => reset(stageId), [reset, stageId])
  // 지원자 카드를 열어 둔 동안 Chat으로 빼도 체크가 풀리도록 선택 지원자 칸이 아니라 여기서 맞춘다
  useEffect(() => {
    if (selectedRows) syncSelection(selectedRows.map((row) => row.applicationId))
  }, [selectedRows, syncSelection])
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
      <h1 className="sr-only">{data.name}</h1>
      <StageStepper overview={data} actions={<StageBar overview={data} />} />
      {/* 칸 사이 경계선으로 너비를 바꾼다. 최소 너비가 있어 칸이 겹치거나 사라지지 않고,
          창 크기가 바뀌면 양옆은 너비를 유지하고 가운데가 늘고 준다 */}
      <ResizablePanelGroup
        id="stage-panels"
        className="min-h-0 flex-1"
        defaultLayout={layout.defaultLayout}
        onLayoutChanged={layout.onLayoutChanged}
      >
        <ResizablePanel
          id="stage-candidates"
          className="flex flex-col"
          defaultSize={300}
          minSize={240}
          groupResizeBehavior="preserve-pixel-size"
        >
          <CandidateList overview={data} editable={editable} />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="stage-main" className="flex flex-col" minSize={420}>
          <section className="flex min-h-0 flex-1 flex-col">
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
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel
          id="stage-chat"
          className="flex flex-col"
          defaultSize={340}
          minSize={280}
          groupResizeBehavior="preserve-pixel-size"
        >
          <ChatPanel overview={data} />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
