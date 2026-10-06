import { Center, Loader } from '@mantine/core'
import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import type { Role } from './api'
import { homePath, useMe } from './auth'
import CabinetLayout from './components/CabinetLayout'
import AssessmentPage from './pages/AssessmentPage'
import CandidateInvitationsPage from './pages/CandidateInvitationsPage'
import CandidateProfilePage from './pages/CandidateProfilePage'
import CandidatesPage from './pages/CandidatesPage'
import ChallengesPage from './pages/ChallengesPage'
import CompanyPage from './pages/CompanyPage'
import EmployerChallengesPage from './pages/EmployerChallengesPage'
import EmployerInvitationsPage from './pages/EmployerInvitationsPage'
import EmployerVacanciesPage from './pages/EmployerVacanciesPage'
import FspCallbackPage from './pages/FspCallbackPage'
import FspIdPage from './pages/FspIdPage'
import LoginPage from './pages/LoginPage'
import NeedPage from './pages/NeedPage'
import NeedsPage from './pages/NeedsPage'
import RegisterPage from './pages/RegisterPage'
import SettingsPage from './pages/SettingsPage'
import VacanciesPage from './pages/VacanciesPage'
import VerifyPage from './pages/VerifyPage'

function Guard({ role, children }: { role?: Role; children: ReactNode }) {
  const { data: user, isPending } = useMe()
  if (isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to={homePath(user)} replace />
  return children
}

function Home() {
  const { data: user } = useMe()
  return <Navigate to={user ? homePath(user) : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify" element={<VerifyPage />} />
      <Route path="/fsp-id" element={<FspIdPage />} />
      <Route path="/fsp-callback" element={<FspCallbackPage />} />
      <Route
        path="/candidate"
        element={
          <Guard role="candidate">
            <CabinetLayout />
          </Guard>
        }
      >
        <Route path="assessment" element={<AssessmentPage />} />
        <Route path="invitations" element={<CandidateInvitationsPage />} />
        <Route path="vacancies" element={<VacanciesPage />} />
        <Route path="challenges" element={<ChallengesPage />} />
        <Route path="profile" element={<CandidateProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route
        path="/employer"
        element={
          <Guard role="employer">
            <CabinetLayout />
          </Guard>
        }
      >
        <Route path="needs" element={<NeedsPage />} />
        <Route path="needs/:id" element={<NeedPage />} />
        <Route path="candidates" element={<CandidatesPage />} />
        <Route path="invitations" element={<EmployerInvitationsPage />} />
        <Route path="vacancies" element={<EmployerVacanciesPage />} />
        <Route path="challenges" element={<EmployerChallengesPage />} />
        <Route path="company" element={<CompanyPage />} />
      </Route>
      <Route
        path="*"
        element={
          <Guard>
            <Home />
          </Guard>
        }
      />
    </Routes>
  )
}
