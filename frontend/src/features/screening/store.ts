import { create } from 'zustand'

export type Mention = { applicationId: string; name: string }

/** 전형 화면의 화면 상태: 체크한 지원자, 열린 지원자 카드, Chat 입력창의 지원자 칩. 전형이나 탭을 바꾸면 비운다. */
type StageUiState = {
  /** 지금 화면의 전형과 탭 (전형:탭) */
  scope: string | null
  checked: string[]
  /** 마지막으로 받은 선택 지원자. 목록이 바뀌면 빠진 지원자를 찾는 데 쓴다 */
  selection: string[] | null
  openId: string | null
  mentions: Mention[]
  reset: (scope: string) => void
  toggleChecked: (applicationId: string, value?: boolean) => void
  setChecked: (applicationIds: string[]) => void
  syncSelection: (applicationIds: string[]) => void
  open: (candidate: Mention | null) => void
  addMention: (mention: Mention) => void
  removeMention: (applicationId: string) => void
  clearMentions: () => void
}

export const useStageUi = create<StageUiState>((set) => ({
  scope: null,
  checked: [],
  selection: null,
  openId: null,
  mentions: [],
  reset: (scope) =>
    set((state) =>
      state.scope === scope
        ? state
        : { scope, checked: [], selection: null, openId: null, mentions: [] },
    ),
  toggleChecked: (applicationId, value) =>
    set((state) => {
      const on = value ?? !state.checked.includes(applicationId)
      const rest = state.checked.filter((id) => id !== applicationId)
      return { checked: on ? [...rest, applicationId] : rest }
    }),
  setChecked: (checked) => set({ checked }),
  // 비우기, 빼기, Chat으로 선택 지원자에서 빠진 지원자는 체크도 푼다 (FR-22)
  syncSelection: (selection) =>
    set((state) => ({
      selection,
      checked: state.checked.filter(
        (id) => !state.selection?.includes(id) || selection.includes(id),
      ),
    })),
  // 행이나 카드를 누르면 카드가 열리고 Chat 입력창에 칩이 들어간다 (STG-06)
  open: (candidate) =>
    set((state) => ({
      openId: candidate?.applicationId ?? null,
      mentions:
        candidate &&
        !state.mentions.some((mention) => mention.applicationId === candidate.applicationId)
          ? [candidate]
          : state.mentions,
    })),
  addMention: (mention) =>
    set((state) =>
      state.mentions.some((item) => item.applicationId === mention.applicationId)
        ? state
        : { mentions: [...state.mentions, mention] },
    ),
  removeMention: (applicationId) =>
    set((state) => ({
      mentions: state.mentions.filter((mention) => mention.applicationId !== applicationId),
    })),
  clearMentions: () => set({ mentions: [] }),
}))
