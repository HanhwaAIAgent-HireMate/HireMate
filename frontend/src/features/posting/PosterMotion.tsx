import { Pause, Play } from 'lucide-react'
import { useState } from 'react'
import type { PosterDesign } from './poster-design'

/** 글과 본문은 고정하고 상단에만 장식한다. 인쇄에서는 같은 장식의 정지 구도를 쓴다. */
export function PosterMotion({ effect }: { effect: PosterDesign['motion'] }) {
  const [paused, setPaused] = useState(false)
  if (!effect || effect === 'NONE' || effect === 'WAVE') return null
  return (
    <div className="poster-motion" data-effect={effect} data-paused={paused}>
      <div className="poster-motion-effects" aria-hidden="true">
        <div className="poster-motion-glow" />
      </div>
      <button
        type="button"
        className="poster-motion-control"
        aria-label={paused ? '포스터 움직임 재생' : '포스터 움직임 일시정지'}
        aria-pressed={paused}
        onClick={() => setPaused((value) => !value)}
      >
        {paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
      </button>
    </div>
  )
}
