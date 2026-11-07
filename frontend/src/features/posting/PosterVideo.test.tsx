import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PosterVideo } from './PosterVideo'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('재생 중인 원본 영상도 제어 버튼을 요청하지 않으면 정지 버튼을 표시하지 않는다', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  render(
    <PosterVideo
      url="https://storage.orshot.com/test/photo.mp4"
      ratio={1}
      headerHeight={30}
      overlay="<svg/>"
      showControls={false}
      preserveAspectRatio
    />,
  )
  fireEvent.playing(screen.getByLabelText('포스터 원본 배경 영상'))
  expect(screen.queryByRole('button', { name: '포스터 움직임 일시정지' })).not.toBeInTheDocument()
})

it('원본 전체 영상은 컨테이너 높이에 맞춰 세로로 압축하지 않는다', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  render(
    <PosterVideo
      url="https://storage.orshot.com/test/native.mp4"
      ratio={4}
      headerHeight={30}
      overlay="<svg/>"
      preserveAspectRatio
    />,
  )
  expect(screen.getByLabelText('포스터 원본 배경 영상')).toHaveStyle({
    height: 'auto',
    objectFit: 'contain',
  })
})

it('원본 배경은 재생하고 글자는 고정하며 일시정지와 재생을 지원한다', () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
  const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  render(
    <PosterVideo
      url="https://storage.orshot.com/test/background.mp4"
      ratio={600 / 360}
      headerHeight={30}
      overlay="<svg><text>AX 개발자</text></svg>"
    />,
  )
  const video = screen.getByLabelText('포스터 원본 배경 영상')
  expect(play).toHaveBeenCalledOnce()
  expect(video).toHaveAttribute('loop')
  fireEvent.playing(video)
  fireEvent.click(screen.getByRole('button', { name: '포스터 움직임 일시정지' }))
  expect(pause).toHaveBeenCalledOnce()
  expect(screen.getByText('AX 개발자').closest('video')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '포스터 움직임 재생' }))
  expect(play).toHaveBeenCalledTimes(2)
})

it('움직임 축소를 선택한 사용자는 원본 영상을 자동 재생하지 않는다', () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
  const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.stubGlobal('matchMedia', () => ({
    matches: true,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  render(
    <PosterVideo
      url="https://storage.orshot.com/test/background.mp4"
      ratio={1}
      headerHeight={30}
      overlay="<svg/>"
    />,
  )
  expect(play).not.toHaveBeenCalled()
  expect(pause).toHaveBeenCalledOnce()
})
