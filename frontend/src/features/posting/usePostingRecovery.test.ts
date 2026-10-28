import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { usePostingRecovery } from '@/features/posting/usePostingRecovery'

beforeEach(() => sessionStorage.clear())

describe('공고 편집 복구', () => {
  it('새로 열면 같은 공고의 미저장 내용을 복구하고 다른 공고와 공유하지 않는다', () => {
    const saved = { title: '원본', duties: ['업무'] }
    const first = renderHook(() => usePostingRecovery('one', saved))
    act(() => first.result.current.setValue({ ...saved, title: '미저장' }))
    first.unmount()
    const reopened = renderHook(() => usePostingRecovery('one', saved))
    expect(reopened.result.current.value.title).toBe('미저장')
    expect(reopened.result.current.restored).toBe(true)
    const other = renderHook(() => usePostingRecovery('two', saved))
    expect(other.result.current.value.title).toBe('원본')
  })

  it('서버에서 공고가 바뀌었으면 예전 편집으로 덮어쓰지 않는다', () => {
    const initial = { title: '이전' }
    const first = renderHook(() => usePostingRecovery('one', initial))
    act(() => first.result.current.setValue({ title: '로컬' }))
    first.unmount()
    const reopened = renderHook(() => usePostingRecovery('one', { title: '다른 탭에서 저장' }))
    expect(reopened.result.current.value.title).toBe('다른 탭에서 저장')
    expect(reopened.result.current.restored).toBe(false)
  })

  it('저장 성공 후 복구본을 지우며 게시한 공고는 복구하지 않는다', () => {
    const hook = renderHook(({ title }) => usePostingRecovery('one', { title }), {
      initialProps: { title: '원본' },
    })
    act(() => hook.result.current.setValue({ title: '저장할 내용' }))
    hook.rerender({ title: '저장할 내용' })
    expect(hook.result.current.dirty).toBe(false)
    expect(sessionStorage.getItem('hiremate:posting:one')).toBeNull()
  })

  it('손상된 복구 데이터는 무시하고 미저장 변경에만 이탈 경고를 낸다', () => {
    sessionStorage.setItem('hiremate:posting:one', 'broken json')
    const hook = renderHook(() => usePostingRecovery('one', { title: '원본' }))
    expect(hook.result.current.restored).toBe(false)
    act(() => hook.result.current.setValue({ title: '편집' }))
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    hook.unmount()
    const published = renderHook(() => usePostingRecovery('one', { title: '원본' }, false))
    expect(published.result.current.value.title).toBe('원본')
  })
})
