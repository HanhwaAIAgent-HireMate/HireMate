import { Link, Outlet } from 'react-router'

// 로고를 누르면 채용 대시보드로, 오른쪽 위에서 설정을 연다 (기획 v7 §20)
export function HrLayout() {
  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <Link to="/hr" className="font-bold">
          HireMate
        </Link>
        <Link to="/hr/settings" className="text-sm">
          설정
        </Link>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  )
}
