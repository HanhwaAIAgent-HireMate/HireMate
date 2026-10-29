import { beforeEach, describe, expect, it } from 'vitest'

import { useStageUi } from '@/features/screening/store'

describe('useStageUi', () => {
  beforeEach(() => {
    useStageUi.setState({ scope: null })
    useStageUi.getState().reset('s1')
  })

  it('선택 지원자에서 빠진 지원자의 체크를 푼다', () => {
    const { syncSelection, setChecked } = useStageUi.getState()
    syncSelection(['a', 'b', 'c'])
    setChecked(['a', 'b'])

    syncSelection(['b', 'c'])

    expect(useStageUi.getState().checked).toEqual(['b'])
  })

  it('선택 지원자를 비우면 체크가 모두 풀린다', () => {
    const { syncSelection, setChecked } = useStageUi.getState()
    syncSelection(['a', 'b'])
    setChecked(['a', 'b'])

    syncSelection([])

    expect(useStageUi.getState().checked).toEqual([])
  })

  it('선택 지원자 밖에서 체크한 지원자는 그대로 둔다', () => {
    const { syncSelection, setChecked } = useStageUi.getState()
    syncSelection(['a'])
    setChecked(['a', 'x'])

    syncSelection(['a', 'b'])

    expect(useStageUi.getState().checked).toEqual(['a', 'x'])
  })

  it('다른 전형으로 가면 이전 전형의 선택 지원자를 잊는다', () => {
    const { syncSelection, reset } = useStageUi.getState()
    syncSelection(['a'])
    reset('s2')
    useStageUi.getState().setChecked(['a'])

    syncSelection([])

    expect(useStageUi.getState().checked).toEqual(['a'])
  })
})
