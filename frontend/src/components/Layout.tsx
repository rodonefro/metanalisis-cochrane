import { useEffect, useState } from 'react'
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Home, Menu, Plus, X } from 'lucide-react'

function SidebarContent({ onNavigate }: { onNavigate: (to: string) => void }) {
  return (
    <>
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
      <div className="p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <button
          onClick={() => onNavigate('/reviews/new')}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-white text-cochrane-700 text-sm font-semibold rounded-lg hover:bg-cochrane-50 transition-colors"
        >
          <Plus size={16} /> Nueva Revisión
        </button>
      </div>
    </>
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => setMenuOpen(false), [location.pathname])

  return (
    <div className="min-h-screen md:flex">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-56 bg-cochrane-700 text-white flex-col shrink-0 sticky top-0 h-screen">
        <SidebarContent onNavigate={navigate} />
      </aside>

      {/* Mobile top bar */}
      <header className="md:hidden sticky top-0 z-40 bg-cochrane-700 text-white flex items-center justify-between px-4 pt-[env(safe-area-inset-top)] h-[calc(3.25rem+env(safe-area-inset-top))]">
        <button onClick={() => setMenuOpen(true)} aria-label="Abrir menú" className="p-2 -ml-2">
          <Menu size={22} />
        </button>
        <span className="font-bold">MetaAnálisis</span>
        <button onClick={() => navigate('/reviews/new')} aria-label="Nueva revisión" className="p-2 -mr-2">
          <Plus size={22} />
        </button>
      </header>

      {/* Mobile drawer */}
      {menuOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <aside className="w-64 max-w-[80%] bg-cochrane-700 text-white flex flex-col pt-[env(safe-area-inset-top)]">
            <div className="flex justify-end p-2">
              <button onClick={() => setMenuOpen(false)} aria-label="Cerrar menú" className="p-2">
                <X size={22} />
              </button>
            </div>
            <SidebarContent onNavigate={navigate} />
          </aside>
          <button className="flex-1 bg-black/40" aria-label="Cerrar menú" onClick={() => setMenuOpen(false)} />
        </div>
      )}

      <main className="flex-1 min-w-0">
        <Outlet />
      </main>
    </div>
  )
}
