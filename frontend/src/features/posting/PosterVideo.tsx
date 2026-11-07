import { Pause, Play } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

/** 원본 배경 위에 편집 가능한 헤더를 표시한다. 출력·움직임 축소 설정에는 정지 SVG를 사용한다. */
export function PosterVideo({
  url,
  ratio,
  headerHeight,
  overlay,
  preserveAspectRatio = false,
  showControls = true,
  frame,
}: {
  url: string
  ratio: number
  headerHeight: number
  overlay: string
  preserveAspectRatio?: boolean
  showControls?: boolean
  frame?: { left: number; top: number; width: number; height: number }
}) {
  const video = useRef<HTMLVideoElement>(null)
  const [paused, setPaused] = useState(false)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => {
      if (reduced.matches || paused) video.current?.pause()
      else if (video.current) {
        void video.current.play().catch(() => setReady(false))
      }
    }
    sync()
    reduced.addEventListener('change', sync)
    return () => reduced.removeEventListener('change', sync)
  }, [paused, url])
  return (
    <div
      className="poster-video-region absolute inset-x-0 top-0 overflow-hidden"
      data-ready={ready}
      style={{ height: `${headerHeight}%` }}
    >
      <video
        ref={video}
        src={url}
        muted
        loop
        playsInline
        preload="auto"
        aria-label="포스터 원본 배경 영상"
        onPlaying={() => setReady(true)}
        onError={() => setReady(false)}
        className="absolute"
        style={{
          left: frame ? `${frame.left}%` : 0,
          top: frame ? `${frame.top}%` : 0,
          width: frame ? `${frame.width}%` : '100%',
          height: frame ? `${frame.height}%` : preserveAspectRatio ? 'auto' : `${ratio * 100}%`,
          objectFit: 'contain',
          opacity: ready ? 1 : 0,
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
          style={
            frame
              ? {
                  right: `calc(${100 - frame.left - frame.width}% + 8px)`,
                  bottom: `calc(${100 - frame.top - frame.height}% + 8px)`,
                }
              : undefined
          }
          onClick={() => setPaused((value) => !value)}
        >
          {paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
        </button>
      )}
    </div>
  )
}
