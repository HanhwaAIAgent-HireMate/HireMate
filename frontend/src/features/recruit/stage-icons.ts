import {
  Armchair,
  Stethoscope,
  BadgeCheck,
  ClipboardCheck,
  CodeXml,
  FileText,
  MessagesSquare,
  Presentation,
  Users,
  Video,
  type LucideIcon,
} from 'lucide-react'
import type { StageType } from '@/features/recruit/labels'
import type { Schemas } from '@/lib/api/client'

export type StageIconName = NonNullable<Schemas['PostingStage']['icon']>

export const STAGE_ICONS = [
  { id: 'AUTO', label: '기본', component: FileText },
  { id: 'FILE_TEXT', label: '문서', component: FileText },
  { id: 'CLIPBOARD_CHECK', label: '체크리스트', component: ClipboardCheck },
  { id: 'CODE', label: '코드', component: CodeXml },
  { id: 'PRESENTATION', label: '발표', component: Presentation },
  { id: 'MESSAGES', label: '대화', component: MessagesSquare },
  { id: 'USERS', label: '사람', component: Users },
  { id: 'VIDEO', label: '화상', component: Video },
  { id: 'BADGE_CHECK', label: '배지', component: BadgeCheck },
  { id: 'CHAIR', label: '실무면접', component: Armchair },
  { id: 'HEALTH', label: '검진', component: Stethoscope },
  { id: 'NONE', label: '없음', component: null },
] as const satisfies readonly { id: StageIconName; label: string; component: LucideIcon | null }[]

export function resolvedStageIcon(
  type: StageType,
  icon?: StageIconName | null,
  name = '',
): StageIconName {
  if (icon && icon !== 'AUTO') return icon
  if (name.includes('검진')) return 'HEALTH'
  if (name.includes('코딩')) return 'CODE'
  if (type === 'INTERVIEW' && (name.replace(/\s/g, '').includes('2차') || name.includes('최종'))) {
    return 'USERS'
  }
  if (name.includes('실무') && type === 'INTERVIEW') return 'CHAIR'
  const defaults: Record<StageType, StageIconName> = {
    DOCUMENT: 'FILE_TEXT',
    ASSESSMENT: 'CLIPBOARD_CHECK',
    INTERVIEW: 'MESSAGES',
  }
  return defaults[type]
}
