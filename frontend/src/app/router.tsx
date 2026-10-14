import { createBrowserRouter, Navigate } from 'react-router'

import { CareersPage } from '@/pages/careers/CareersPage'
import { HrHomePage } from '@/pages/hr/HrHomePage'

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/hr" replace /> },
  // HR 콘솔 (로그인 후)
  { path: '/hr', element: <HrHomePage /> },
  // 지원자용 채용 페이지
  { path: '/careers/:postingId', element: <CareersPage /> },
])
