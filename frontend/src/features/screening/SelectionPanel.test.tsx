import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'
import type { StageOverview } from '@/features/screening/api'
import { SelectionPanel } from '@/features/screening/SelectionPanel'
import type { StageTab } from '@/features/screening/tabs'

vi.mock('@/features/screening/api', () => ({
  useSelection: () => ({ data: { items: [], total: 0 } }),
  useSelectionActions: () => ({}),
}))
vi.mock('@/features/screening/store', () => ({
  useStageUi: () => ({
    checked: [],
    toggleChecked: vi.fn(),
    setChecked: vi.fn(),
    open: vi.fn(),
    showTable: vi.fn(),
  }),
}))
vi.mock('@/features/report/api', () => ({
  useRequestCompareReport: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/features/report/AgentReportModal', () => ({ AgentReportModal: () => null }))
vi.mock('@/features/report/ReportWindow', () => ({ ReportWindow: () => null }))

function panel(type: StageOverview['type']) {
  const overview = { stageId: 's1', type } as StageOverview
  return render(
    <TooltipProvider>
      <SelectionPanel overview={overview} tab={{ id: 't1' } as StageTab} editable />
    </TooltipProvider>,
  )
}

describe('SelectionPanel 리포트 생성', () => {
  it('서류 전형에서만 리포트 생성 버튼을 보여 준다', () => {
    panel('DOCUMENT')
    expect(screen.getByRole('button', { name: '리포트 생성' })).toBeInTheDocument()
  })

  it.each(['ASSESSMENT', 'INTERVIEW'] as const)('%s 전형에서는 리포트 생성 버튼이 없다', (type) => {
    panel(type)
    expect(screen.queryByRole('button', { name: '리포트 생성' })).not.toBeInTheDocument()
  })
})
