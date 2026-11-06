import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import {
  type LayoutStorage,
  type PanelImperativeHandle,
  useDefaultLayout,
} from 'react-resizable-panels'
import { useParams } from 'react-router'

import { useHeaderCrumb } from '@/app/header-store'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Skeleton } from '@/components/ui/skeleton'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { useStageSuggestions } from '@/features/chat/suggestions'
import { careersPath, RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import {
  stageKeys,
  useSelection,
  useStageOverview,
  type StageOverview,
} from '@/features/screening/api'
import { CandidateCard } from '@/features/screening/CandidateCard'
import { CandidateList } from '@/features/screening/CandidateList'
import { DecisionBar } from '@/features/screening/DecisionBar'
import { SelectionPanel } from '@/features/screening/SelectionPanel'
import { StageBar } from '@/features/screening/StageBar'
import { StageStepper } from '@/features/screening/StageHeader'
import { useStageUi } from '@/features/screening/store'
import { TabBar } from '@/features/screening/TabBar'
import { TablePanel } from '@/features/screening/TablePanel'
import { useCurrentTab, type StageTab } from '@/features/screening/tabs'
import { ApiError } from '@/lib/api/client'

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

// AI Chat 칸 기본 · 최소 너비 (px)
const CHAT_DEFAULT = 340
const CHAT_MIN = 280

// Generic Stage Page (STG-01). 서류 · 평가 · 면접 전형이 모두 같은 3단 구조를 쓰고, 지원자 카드의 Viewer만 바뀐다.
// 선택 지원자와 AI Chat 두 칸 위에 탭 바가 있다. 탭은 선택 지원자와 대화의 묶음이고 같은 기업 담당자가 함께 쓴다
export function StagePage() {
  const { stageId = '' } = useParams()
  const overview = useStageOverview(stageId)
  const { tabs, tab, tabId, setTab } = useCurrentTab(stageId)
  const { reset, tableOpen, tableChat, openId } = useStageUi()
  const chat = useRef<PanelImperativeHandle | null>(null)
  // 칸 너비는 PR #110 기준이다 (전체 지원자 300 · 최소 240, 선택 지원자 최소 420, Chat 340 · 최소 280).
  // 예전에 저장한 너비 대신 이 기본값을 쓰도록 id를 바꿨다
  const columns = useDefaultLayout({ id: 'stage-columns', storage: layoutStorage })
  const work = useDefaultLayout({ id: 'stage-work', storage: layoutStorage })

  // 전형이나 탭을 바꾸면 체크, 열린 카드, Chat 입력창 칩을 비운다
  useEffect(() => reset(`${stageId}:${tabId ?? ''}`), [reset, stageId, tabId])
  // 표를 보는 동안만 Chat을 접어 가로를 넓게 쓴다. 표에서 지원자 카드를 열거나, 표를 닫거나, 표의 [AI Chat]을 누르면 다시 편다.
  // 그 밖에는 Chat 칸을 접을 수 없고 최소 너비까지만 줄어든다
  const wide = tableOpen && !openId && !tableChat
  const chatWidth = useRef(CHAT_DEFAULT)
  // Chat 칸은 탭을 받은 뒤에 생기므로 그때도 맞춘다. 표를 보다 떠나 접힌 채 저장된 칸도 여기서 접기 전 너비로 다시 편다
  const chatReady = Boolean(tab && overview.data)
  useEffect(() => {
    const panel = chat.current
    if (!chatReady || !panel) return
    const width = panel.getSize().inPixels
    if (!wide) {
      if (width < CHAT_MIN) panel.resize(chatWidth.current)
      return
    }
    if (width >= CHAT_MIN) chatWidth.current = width
    // 접을 수 있게 바뀐 칸 설정은 다음 프레임에 반영되므로 그때 접는다
    const frame = requestAnimationFrame(() => chat.current?.collapse())
    return () => cancelAnimationFrame(frame)
  }, [wide, chatReady])
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

  return (
    <div className="flex h-full flex-col">
      <h1 className="sr-only">{data.name}</h1>
      <StageStepper overview={data} actions={<StageBar overview={data} />} />
      {/* 칸 사이 경계선으로 너비를 바꾼다. 최소 너비가 있어 칸이 겹치거나 사라지지 않고,
          창 크기가 바뀌면 양옆은 너비를 유지하고 가운데가 늘고 준다 */}
      <ResizablePanelGroup
        id="stage-columns"
        className="min-h-0 flex-1"
        defaultLayout={columns.defaultLayout}
        onLayoutChanged={columns.onLayoutChanged}
      >
        <ResizablePanel
          id="stage-candidates"
          className="flex flex-col"
          // 한 줄에 카드 3장이 아이콘과 이름 네 글자까지 보이는 폭
          defaultSize={390}
          minSize={240}
          groupResizeBehavior="preserve-pixel-size"
        >
          <CandidateList overview={data} tabId={tabId} editable={editable} />
        </ResizablePanel>
        <ResizableHandle withHandle />
        {/* 오른쪽 묶음 최소 너비 = 선택 지원자 최소 420 + Chat 최소 280 */}
        <ResizablePanel id="stage-workspace" className="flex flex-col" minSize={700}>
          {tab ? (
            <>
              <TabBar
                stageId={data.stageId}
                tabs={tabs.data ?? []}
                current={tab.id}
                onSelect={setTab}
                editable={editable}
              />
              <ResizablePanelGroup
                id="stage-work"
                className="min-h-0 flex-1"
                defaultLayout={work.defaultLayout}
                onLayoutChanged={work.onLayoutChanged}
              >
                <ResizablePanel id="stage-main" className="flex flex-col" minSize={420}>
                  <Workspace overview={data} tab={tab} editable={editable} />
                </ResizablePanel>
                <ResizableHandle withHandle />
                <ResizablePanel
                  id="stage-chat"
                  panelRef={chat}
                  className="flex flex-col"
                  defaultSize={CHAT_DEFAULT}
                  minSize={CHAT_MIN}
                  collapsible={wide}
                  collapsedSize={0}
                  groupResizeBehavior="preserve-pixel-size"
                >
                  <StageChat overview={data} tabId={tab.id} />
                </ResizablePanel>
              </ResizablePanelGroup>
            </>
          ) : tabs.isPending ? (
            <Skeleton className="m-4 h-96" />
          ) : (
            <p className="p-6 text-sm text-muted-foreground">
              전형을 시작하면 선택 지원자와 AI Chat을 쓸 수 있어요.
            </p>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

/** 가운데 칸: 지금 탭의 선택 지원자, 표 보기나 열린 지원자 카드, 그리고 결정 바 */
function Workspace({
  overview,
  tab,
  editable,
}: {
  overview: StageOverview
  tab: StageTab
  editable: boolean
}) {
  const queryClient = useQueryClient()
  const selection = useSelection(overview.stageId, tab.id)
  const { openId, tableOpen, syncSelection } = useStageUi()
  const selectedRows = selection.data?.items

  // 지원자 카드를 열어 둔 동안 Chat으로 빼도 체크가 풀리도록 선택 지원자 칸이 아니라 여기서 맞춘다
  useEffect(() => {
    if (selectedRows) syncSelection(selectedRows.map((row) => row.applicationId))
  }, [selectedRows, syncSelection])
  // 다른 담당자가 이 탭을 지웠으면 탭 목록을 다시 받아 남은 탭을 연다
  const gone = selection.error instanceof ApiError && selection.error.code === 'TAB_NOT_FOUND'
  useEffect(() => {
    if (gone) void queryClient.invalidateQueries({ queryKey: stageKeys.tabs(overview.stageId) })
  }, [gone, queryClient, overview.stageId])

  const names = Object.fromEntries((selectedRows ?? []).map((row) => [row.applicationId, row.name]))
  return (
    <section className="flex min-h-0 flex-1 flex-col">
      {openId ? (
        <CandidateCard
          key={openId}
          overview={overview}
          applicationId={openId}
          editable={editable}
          selectedCount={tab.selectedCount}
        />
      ) : tableOpen && overview.type === 'DOCUMENT' ? (
        <TablePanel overview={overview} tab={tab} />
      ) : (
        <SelectionPanel overview={overview} tab={tab} editable={editable} />
      )}
      <DecisionBar stageId={overview.stageId} tabId={tab.id} editable={editable} names={names} />
    </section>
  )
}

/** 전형 화면의 AI Chat. 빈 대화의 추천 질문을 전형 상황(상태, 결정 현황, 공고 기준, 고른 지원자)에 맞춘다 */
function StageChat({ overview, tabId }: { overview: StageOverview; tabId: string }) {
  const examples = useStageSuggestions(overview)
  return <ChatPanel overview={overview} tabId={tabId} examples={examples} />
}
