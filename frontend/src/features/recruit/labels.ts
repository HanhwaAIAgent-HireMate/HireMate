import type { Schemas } from '@/lib/api/client'

export type StageType = Schemas['PostingStage']['type']
export type RecruitmentStatus = Schemas['PostingView']['status']

export const STAGE_TYPE_LABELS: Record<StageType, string> = {
  DOCUMENT: '서류',
  ASSESSMENT: '평가',
  INTERVIEW: '면접',
}

export const RECRUITMENT_STATUS_LABELS: Record<RecruitmentStatus, string> = {
  DRAFT: '작성 중',
  PUBLISHED: '공고 게시 중',
  IN_PROGRESS: '전형 진행 중',
  CLOSED: '채용 종료',
}

/** 지원자용 채용 페이지 주소 */
export function careersPath(postingId: string) {
  return `/careers/${postingId}`
}
