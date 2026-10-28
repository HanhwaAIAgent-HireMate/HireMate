import type { CSSProperties } from 'react'
import { StageIllustration, type StageIconName } from '@/features/recruit/StageIcon'
import type { StageType } from '@/features/recruit/labels'
import './stage-process.css'

export function StageProcess({
  stages,
  includeFinal = false,
  color = '#2459a6',
}: {
  stages: { name: string; type?: StageType; icon?: StageIconName | null }[]
  includeFinal?: boolean
  color?: string
}) {
  const items = includeFinal
    ? [...stages, { name: '최종 합격', type: 'INTERVIEW' as const, icon: 'BADGE_CHECK' as const }]
    : stages
  return (
    <ol
      className="stage-process"
      aria-label="전형 절차"
      style={
        {
          '--stage-count': Math.min(items.length, 5),
          '--stage-color': /^#[0-9a-f]{6}$/i.test(color) ? color : '#2459a6',
        } as CSSProperties
      }
    >
      {items.map((stage, index) => (
        <li key={`${stage.name}-${index}`}>
          <StageIllustration
            type={stage.type ?? 'INTERVIEW'}
            icon={stage.icon}
            name={stage.name}
            color={color}
          />
          <span>{stage.name}</span>
        </li>
      ))}
    </ol>
  )
}
