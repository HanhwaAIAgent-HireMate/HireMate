import { Plus, X } from 'lucide-react'
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
import { MAX_TABS, neighborTab, useTabActions, type StageTab } from '@/features/screening/tabs'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

/**
 * 선택 지원자와 AI Chat 두 칸 위의 탭 바. 탭은 선택 지원자와 대화의 묶음이고 같은 기업 담당자가 함께 쓴다.
 * 이름을 두 번 누르면 바꾼다. 끝난 전형(editable=false)에서는 만들거나 지울 수 없고 이름만 바꾼다.
 */
export function TabBar({
  stageId,
  tabs,
  current,
  onSelect,
  editable,
}: {
  stageId: string
  tabs: StageTab[]
  current: string
  onSelect: (tabId: string) => void
  editable: boolean
}) {
  const actions = useTabActions(stageId)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [removing, setRemoving] = useState<StageTab | null>(null)
  const fail = (error: unknown) => toast.error(errorMessage(error))

  const save = (tab: StageTab) => {
    const name = draft.trim()
    setEditing(null)
    if (name && name !== tab.name) actions.rename.mutate({ tabId: tab.id, name }, { onError: fail })
  }
  const remove = (tab: StageTab) => {
    setRemoving(null)
    actions.remove.mutate(tab.id, {
      onSuccess: () => {
        const next = neighborTab(tabs, tab.id)
        if (tab.id === current && next) onSelect(next)
      },
      onError: fail,
    })
  }

  return (
    <div className="flex h-10 shrink-0 items-stretch border-b px-3">
      <div
        role="tablist"
        aria-label="탭"
        className="flex min-w-0 items-stretch gap-0.5 overflow-hidden"
      >
        {tabs.map((tab) => {
          const active = tab.id === current
          return (
            <div
              key={tab.id}
              className={cn(
                'group @container/tab relative flex w-56 min-w-0 items-center gap-1 border-b-2 px-1',
                active ? 'border-foreground' : 'border-transparent',
              )}
            >
              {editing === tab.id ? (
                <input
                  autoFocus
                  aria-label="탭 이름"
                  value={draft}
                  maxLength={30}
                  onChange={(event) => setDraft(event.target.value)}
                  onBlur={() => save(tab)}
                  onKeyDown={(event) => {
                    if (event.nativeEvent.isComposing) return
                    if (event.key === 'Enter') save(tab)
                    if (event.key === 'Escape') setEditing(null)
                  }}
                  className="w-full min-w-0 rounded border bg-background px-1.5 py-0.5 text-[13px] outline-none"
                />
              ) : (
                <button
                  role="tab"
                  aria-selected={active}
                  aria-label={
                    tab.selectedCount > 0
                      ? `${tab.name} (선택 지원자 ${tab.selectedCount}명)`
                      : tab.name
                  }
                  onClick={() => onSelect(tab.id)}
                  onDoubleClick={() => {
                    setDraft(tab.name)
                    setEditing(tab.id)
                  }}
                  title={`${tab.name} (두 번 누르면 이름을 바꿔요)`}
                  className={cn(
                    'inline-flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden text-[13px] whitespace-nowrap after:absolute after:inset-0',
                    active
                      ? 'font-semibold text-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <span className="min-w-0 flex-1 truncate text-left">{tab.name}</span>
                  {tab.selectedCount > 0 && (
                    <span className="hidden h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-full bg-muted px-1.5 text-[11px] font-semibold text-muted-foreground tabular-nums @min-[4rem]/tab:inline-flex">
                      {tab.selectedCount}
                    </span>
                  )}
                </button>
              )}
              {editable && tabs.length > 1 && editing !== tab.id && (
                <button
                  aria-label={`${tab.name} 지우기`}
                  onClick={() => setRemoving(tab)}
                  className={cn(
                    'relative shrink-0 rounded text-muted-foreground hover:bg-muted hover:text-foreground @min-[4rem]/tab:p-0.5',
                    !active && 'opacity-60',
                  )}
                >
                  <X className="size-3 @min-[4rem]/tab:size-3.5" />
                </button>
              )}
            </div>
          )
        })}
      </div>
      {editable && (
        <button
          aria-label="새 탭"
          title={tabs.length >= MAX_TABS ? `탭은 ${MAX_TABS}개까지 만들 수 있어요` : '새 탭'}
          disabled={tabs.length >= MAX_TABS || actions.create.isPending}
          onClick={() =>
            actions.create.mutate(undefined, {
              onSuccess: (tab) => onSelect(tab.id),
              onError: fail,
            })
          }
          className="ml-1 flex size-7 shrink-0 items-center justify-center self-center rounded-lg border text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          <Plus className="size-4" />
        </button>
      )}
      <AlertDialog open={removing !== null} onOpenChange={(open) => !open && setRemoving(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{removing?.name} 탭을 지울까요?</AlertDialogTitle>
            <AlertDialogDescription>
              이 탭의 선택 지원자와 대화가 모두 지워져요. 함께 쓰는 담당자에게도 사라져요.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <Button variant="destructive" onClick={() => removing && remove(removing)}>
              지우기
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
