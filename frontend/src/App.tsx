import { Suspense, lazy } from "react"
import { Routes, Route, Navigate, Outlet } from "react-router"
import { useAuthStore } from "@/stores/auth-store"

const HomePage = lazy(() => import("@/pages/HomePage"))
const LoginPage = lazy(() => import("@/pages/LoginPage"))
const RegisterPage = lazy(() => import("@/pages/RegisterPage"))
const AppLayout = lazy(() => import("@/layouts/AppLayout"))
const CaseListPage = lazy(() => import("@/pages/CaseListPage"))
const DashboardPage = lazy(() => import("@/pages/DashboardPage"))
const WorkspacePage = lazy(() => import("@/pages/WorkspacePage"))
const EvidencePage = lazy(() => import("@/pages/EvidencePage"))
const TimelinePage = lazy(() => import("@/pages/TimelinePage"))
const ComplaintPage = lazy(() => import("@/pages/ComplaintPage"))
const MaskPage = lazy(() => import("@/pages/MaskPage"))
const ExportPage = lazy(() => import("@/pages/ExportPage"))

function AuthGuard() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

function PublicOnly() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (isAuthenticated) {
    return <Navigate to="/cases" replace />
  }
  return <Outlet />
}

function PageLoader() {
  return (
    <div className="flex h-64 items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
    </div>
  )
}

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        {/* 公开落地页 */}
        <Route path="/home" element={<HomePage />} />
        <Route element={<PublicOnly />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>
        <Route element={<AuthGuard />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/home" replace />} />
            <Route path="/cases" element={<CaseListPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/cases/:caseId/workspace" element={<WorkspacePage />} />
            <Route path="/cases/:caseId/evidence" element={<EvidencePage />} />
            <Route path="/cases/:caseId/timeline" element={<TimelinePage />} />
            <Route path="/cases/:caseId/complaint" element={<ComplaintPage />} />
            <Route path="/cases/:caseId/mask" element={<MaskPage />} />
            <Route path="/cases/:caseId/export" element={<ExportPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/home" replace />} />
      </Routes>
    </Suspense>
  )
}
