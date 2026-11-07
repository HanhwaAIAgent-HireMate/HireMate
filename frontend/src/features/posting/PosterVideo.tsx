import { Pause, Play } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'

/** 원본 배경 위에 편집 가능한 헤더를 표시한다. 출력·움직임 축소 설정에는 정지 SVG를 사용한다. */
export function PosterVideo({
  url,
  ratio,
  headerHeight,
  overlay,
  zoom = 1,
  revealHeader = false,
  preserveAspectRatio = false,
  showControls = true,
}: {
  url: string
  ratio: number
  headerHeight: number
  overlay: string
  zoom?: number
  revealHeader?: boolean
  preserveAspectRatio?: boolean
  showControls?: boolean
}) {
  const video = useRef<HTMLVideoElement>(null)
  const [paused, setPaused] = useState(false)
  const [ready, setReady] = useState(false)
  const [duration, setDuration] = useState(0)
  const playbackRate = revealHeader ? 1.25 : 1
  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => {
      if (reduced.matches || paused) video.current?.pause()
      else if (video.current) {
        video.current.playbackRate = playbackRate
        void video.current.play().catch(() => setReady(false))
      }
    }
    sync()
    reduced.addEventListener('change', sync)
    return () => reduced.removeEventListener('change', sync)
  }, [paused, playbackRate, url])
  return (
    <div
      className="poster-video-region absolute inset-x-0 top-0 overflow-hidden"
      data-ready={ready}
      data-reveal={revealHeader && duration > 0}
      data-paused={paused}
      style={
        {
          height: `${headerHeight}%`,
          '--poster-reveal-duration': `${duration / playbackRate}s`,
        } as CSSProperties
      }
    >
      <video
        ref={video}
        src={url}
        muted
        loop
        playsInline
        preload="auto"
        aria-label="포스터 원본 배경 영상"
        onLoadedMetadata={(event) => {
          const length = event.currentTarget.duration
          if (Number.isFinite(length)) setDuration(length)
        }}
        onPlaying={() => setReady(true)}
        onError={() => setReady(false)}
        className="absolute inset-x-0 top-0 w-full"
        style={{
          height: preserveAspectRatio ? 'auto' : `${ratio * 100}%`,
          objectFit: 'contain',
          opacity: ready ? 1 : 0,
          transform: `scaleY(${zoom})`,
          transformOrigin: 'center top',
        }}
      />
      <div
        aria-hidden="true"
        className="poster-vector absolute inset-x-0 top-0 w-full"
        dangerouslySetInnerHTML={{ __html: overlay }}
      />
      {ready && showControls && (
        <button
          type="button"
          className="poster-motion-control"
          aria-label={paused ? '포스터 움직임 재생' : '포스터 움직임 일시정지'}
          aria-pressed={paused}
          onClick={() => setPaused((value) => !value)}
        >
          {paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
        </button>
      )}
    </div>
  )
}
