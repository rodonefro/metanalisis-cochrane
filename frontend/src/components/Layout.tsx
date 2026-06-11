import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { Home, Plus } from 'lucide-react'

export default function Layout() {
  const navigate = useNavigate()
  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-56 bg-cochrane-700 text-white flex flex-col shrink-0">
        <div className="p-5 border-b border-cochrane-600">
          <h1 className="text-lg font-bold leading-tight">MetaAnálisis</h1>
          <p className="text-xs text-cochrane-100 mt-0.5">Plataforma Cochrane</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          <NavLink
            to="/dashboard"
            className={({ isActive }) =>
              `flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-cochrane-500 text-white' : 'text-cochrane-100 hover:bg-cochrane-600'
              }`
            }
          >
            <Home size={16} /> Inicio (Dashboard)
          </NavLink>
        </nav>
        <div className="p-3">
          <button
            onClick={() => navigate('/reviews/new')}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-white text-cochrane-700 text-sm font-semibold rounded-lg hover:bg-cochrane-50 transition-colors"
          >
            <Plus size={16} /> Nueva Revisión
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
