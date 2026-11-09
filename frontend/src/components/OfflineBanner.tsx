import { WifiOff } from 'lucide-react'
import { useSyncExternalStore } from 'react'

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange)
  window.addEventListener('offline', onChange)
  return () => {
    window.removeEventListener('online', onChange)
    window.removeEventListener('offline', onChange)
  }
}

const online = () => navigator.onLine

/**
 * 인터넷 연결이 끊기면 화면 맨 위에 띄우는 띠. 지원자를 눌렀는데 불러오지 못해 회색 자리만 보일 때도 이유를 알 수 있게 한다.
 * 다시 연결되면 사라지고, 화면은 실패한 내용을 다시 불러온다 (TanStack Query의 재연결 시 다시 불러오기).
 * 내 인터넷 문제라 관리자 확인 요청은 붙이지 않는다.
 */
export function OfflineBanner() {
  const connected = useSyncExternalStore(subscribe, online, () => true)
  if (connected) return null
  return (
    <div
      role="alert"
      className="fixed inset-x-0 top-0 z-[60] flex items-center justify-center gap-2 bg-zinc-900 px-4 py-2 text-sm text-white"
    >
      <WifiOff className="size-4 shrink-0" />
      인터넷 연결이 끊겼어요. 연결되면 자동으로 다시 불러와요.
    </div>
  )
}
