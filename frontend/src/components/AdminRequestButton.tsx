import { LifeBuoy } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ADMIN_REQUEST_LABEL, requestAdmin } from '@/lib/admin-request'

/**
 * AI 서버 · 서버 오류 안내 아래에 붙이는 [관리자에게 확인 요청] 버튼 (QA CM-08).
 * AI 분석 실패 · 리포트 실패 · 안내 초안 실패처럼 AI 작업이 실패한 자리에도 붙인다.
 * 실제 요청은 아직 보내지 않는다 (lib/admin-request의 TODO).
 */
export function AdminRequestButton() {
  return (
    <Button type="button" variant="outline" size="sm" onClick={requestAdmin}>
      <LifeBuoy />
      {ADMIN_REQUEST_LABEL}
    </Button>
  )
}
