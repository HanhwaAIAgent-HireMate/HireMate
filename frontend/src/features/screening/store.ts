import { create } from 'zustand'

export type Mention = { applicationId: string; name: string }

/** 전형 화면의 화면 상태: 체크한 지원자, 열린 지원자 카드, 표 보기, Chat 입력창의 지원자 칩. 전형이나 탭을 바꾸면 비운다. */
type StageUiState = {
  /** 지금 화면의 전형과 탭 (전형:탭) */
  scope: string | null
  checked: string[]
  /** 마지막으로 받은 선택 지원자. 목록이 바뀌면 빠진 지원자를 찾는 데 쓴다 */
  selection: string[] | null
  openId: string | null
  /** 선택 지원자 표 보기를 열었는가. 표를 보는 동안 Chat을 접는다 */
  tableOpen: boolean
  /** 표를 보는 동안 접어 둔 Chat을 HR이 다시 폈는가 */
  tableChat: boolean
  mentions: Mention[]
  reset: (scope: string) => void
  toggleChecked: (applicationId: string, value?: boolean) => void
  setChecked: (applicationIds: string[]) => void
  syncSelection: (applicationIds: string[]) => void
  open: (candidate: Mention | null) => void
  showTable: (open: boolean) => void
  showTableChat: (open: boolean) => void
  addMention: (mention: Mention) => void
  removeMention: (applicationId: string) => void
  clearMentions: () => void
}

export const useStageUi = create<StageUiState>((set) => ({
  scope: null,
  checked: [],
  selection: null,
  openId: null,
  tableOpen: false,
  tableChat: false,
  mentions: [],
  reset: (scope) =>
    set((state) =>
      state.scope === scope
        ? state
        : {
            scope,
            checked: [],
            selection: null,
            openId: null,
            tableOpen: false,
            tableChat: false,
            mentions: [],
          },
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
  // 행이나 카드를 누르면 카드가 열리고 Chat 입력창에 칩이 더해진다 (STG-06). 여러 명을 차례로 누르면 모두 멘션된다
  open: (candidate) =>
    set((state) => ({
      openId: candidate?.applicationId ?? null,
      mentions:
        candidate &&
        !state.mentions.some((mention) => mention.applicationId === candidate.applicationId)
          ? [...state.mentions, candidate]
          : state.mentions,
    })),
  // 표를 열면 열린 카드를 닫는다. 표에서 지원자를 열면 카드가 표 위에 열리고, 뒤로 가면 표로 돌아온다
  // 표를 열 때마다 Chat은 접힌 채로 시작한다
  showTable: (tableOpen) => set({ tableOpen, tableChat: false, openId: null }),
  showTableChat: (tableChat) => set({ tableChat }),
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
