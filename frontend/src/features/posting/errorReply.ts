import type { AiMessage } from '@/features/posting/AiRequestPanel'
import { errorMessage, needsAdmin } from '@/lib/api/client'

/** 요청이 실패했을 때 Chat에 남길 답. AI 서버 오류면 관리자 확인 요청 버튼을 붙인다 */
export function errorReply(error: unknown): AiMessage {
  return { role: 'ai', text: errorMessage(error), admin: needsAdmin(error) }
}
