import { Routes, Route, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import NewReview from './pages/NewReview'
import ReviewEditor from './pages/ReviewEditor'
import Layout from './components/Layout'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/reviews/new" element={<NewReview />} />
        <Route path="/reviews/:id" element={<ReviewEditor />} />
      </Route>
    </Routes>
  )
}
