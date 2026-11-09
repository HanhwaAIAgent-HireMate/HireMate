import { useTheme } from 'next-themes'
import { Toaster as Sonner, type ToasterProps } from 'sonner'
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, Loader2Icon } from 'lucide-react'

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = 'system' } = useTheme()

  return (
    <Sonner
      theme={theme as ToasterProps['theme']}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        // 오류 토스트는 앞의 ⊗ 아이콘을 빼고 문구만 보인다 (닫기 × 와 헷갈리지 않게). null이면 아이콘 칸을 그리지 않는다
        error: null,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          // 모든 토스트(성공 · 오류 · 안내)를 같은 검정 스타일로 보인다. 화면 테마와 상관없이 같다
          '--normal-bg': '#18181b',
          '--normal-text': '#fafafa',
          '--normal-border': '#27272a',
          '--border-radius': 'var(--radius)',
          // 모든 토스트를 같은 폭으로 보인다. 전형 화면 '선택 지원자' 칸의 가장 좁은 폭(420px)과 같다
          '--width': '420px',
          // × 닫기 버튼은 왼쪽 위가 아니라 오른쪽 위 모서리에 둔다
          '--toast-close-button-start': 'unset',
          '--toast-close-button-end': '0',
          '--toast-close-button-transform': 'translate(35%, -35%)',
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: 'cn-toast',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
