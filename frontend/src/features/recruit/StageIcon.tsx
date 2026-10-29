import { useId } from 'react'
import folderImage from './stage-folder.png'
import clipboardImage from './stage-clipboard.png'
import chairImage from './stage-chair.png'
import messagesImage from './stage-messages.png'
import healthImage from './stage-health.png'
import codeImage from './stage-code.png'
import usersImage from './stage-users.png'
import videoImage from './stage-video.png'
import presentationImage from './stage-presentation.png'
import badgeImage from './stage-badge.png'
import { STAGE_ICONS, resolvedStageIcon, type StageIconName } from '@/features/recruit/stage-icons'
import type { StageType } from '@/features/recruit/labels'

export type { StageIconName } from '@/features/recruit/stage-icons'

const IMAGES: Partial<Record<StageIconName, string>> = {
  FILE_TEXT: folderImage,
  CLIPBOARD_CHECK: clipboardImage,
  CHAIR: chairImage,
  MESSAGES: messagesImage,
  HEALTH: healthImage,
  CODE: codeImage,
  USERS: usersImage,
  VIDEO: videoImage,
  PRESENTATION: presentationImage,
  BADGE_CHECK: badgeImage,
}

export function StageIllustration({
  type,
  icon,
  name,
  color = '#2459a6',
}: {
  type: StageType
  icon?: StageIconName | null
  name: string
  color?: string
}) {
  const filterId = `stage-tone-${useId().replace(/:/g, '')}`
  const safe = /^#[0-9a-f]{6}$/i.test(color) ? color : '#2459a6'
  const [red, green, blue] = [1, 3, 5].map(
    (offset) => parseInt(safe.slice(offset, offset + 2), 16) / 255,
  )
  const resolved = resolvedStageIcon(type, icon, name)
  if (resolved === 'NONE') return null
  const src = IMAGES[resolved]
  return (
    <span className="stage-illustration" aria-hidden="true" data-stage-icon={resolved}>
      {src ? (
        <>
          <svg width="0" height="0" className="stage-tone-defs" focusable="false">
            <defs>
              <filter id={filterId} colorInterpolationFilters="sRGB">
                <feColorMatrix type="saturate" values="0" />
                <feComponentTransfer>
                  <feFuncR type="gamma" exponent="1.6" />
                  <feFuncG type="gamma" exponent="1.6" />
                  <feFuncB type="gamma" exponent="1.6" />
                </feComponentTransfer>
                <feComponentTransfer>
                  <feFuncR type="linear" slope={1 - red} intercept={red} />
                  <feFuncG type="linear" slope={1 - green} intercept={green} />
                  <feFuncB type="linear" slope={1 - blue} intercept={blue} />
                </feComponentTransfer>
              </filter>
            </defs>
          </svg>
          <img src={src} alt="" style={{ filter: `url(#${filterId})` }} />
        </>
      ) : (
        <StageIcon type={type} icon={resolved} className="size-9" />
      )}
    </span>
  )
}

/** 표시용 선택은 전형의 업무 종류와 독립적이다. */
export function StageIcon({
  type,
  icon,
  className = 'size-3.5 shrink-0',
}: {
  type: StageType
  icon?: StageIconName | null
  className?: string
}) {
  const resolved = resolvedStageIcon(type, icon)
  if (resolved === 'NONE') return null
  const Icon = STAGE_ICONS.find((item) => item.id === resolved)?.component
  return Icon ? <Icon className={className} aria-hidden="true" data-stage-icon={resolved} /> : null
}
