import { LifeBuoy } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'

/**
 * AI 서버 · 서버 오류 안내 아래에 붙이는 [관리자에게 확인 요청] 버튼 (QA CM-08).
 * TODO: 실제 요청은 아직 보내지 않는다 (화면 확인용). 요청 API를 만들면 onClick에서 부르고 성공했을 때만 알린다.
 */
export function AdminRequestButton() {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => toast.success('관리자에게 확인 요청을 보냈어요.')}
    >
      <LifeBuoy />
      관리자에게 확인 요청
    </Button>
  )
}
