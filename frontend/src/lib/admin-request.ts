import { toast } from 'sonner'

import { errorMessage, needsAdmin } from '@/lib/api/client'

/** [관리자에게 확인 요청] 버튼 글자. 오류 안내 아래 버튼과 오류 토스트의 버튼이 같다 */
export const ADMIN_REQUEST_LABEL = '관리자에게 확인 요청'

/**
 * 관리자에게 확인을 요청한다 (QA CM-08 · CM-11).
 * TODO: 실제 요청은 아직 보내지 않는다 (화면 확인용). 요청 API를 만들면 여기서 부르고 성공했을 때만 알린다.
 */
export function requestAdmin() {
  toast.success('관리자에게 확인 요청을 보냈어요.')
}

/**
 * AI 기능의 요청이 실패했을 때 띄우는 오류 토스트. AI 서버 · 서버 오류면 토스트에 [관리자에게 확인 요청]을 붙인다.
 * 버튼을 누르기 전에 사라지지 않게 이 토스트는 자동으로 닫지 않고, × 로 닫을 때까지 둔다.
 * 그 밖의 오류(입력 잘못, 권한 등)는 문구만 보이고 다른 토스트처럼 금방 사라진다.
 */
export function toastAiError(error: unknown) {
  const message = errorMessage(error)
  if (needsAdmin(error)) {
    toast.error(message, {
      action: { label: ADMIN_REQUEST_LABEL, onClick: requestAdmin },
      duration: Infinity,
      closeButton: true,
    })
  } else {
    toast.error(message)
  }
}
