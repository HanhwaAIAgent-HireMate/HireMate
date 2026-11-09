import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { OfflineBanner } from '@/components/OfflineBanner'

describe('인터넷 끊김 띠', () => {
  afterEach(() => vi.restoreAllMocks())

  it('연결이 끊기면 띠가 보이고, 다시 연결되면 사라진다', () => {
    const onLine = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
    render(<OfflineBanner />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    onLine.mockReturnValue(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    expect(screen.getByRole('alert')).toHaveTextContent('인터넷 연결이 끊겼어요')

    onLine.mockReturnValue(true)
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
