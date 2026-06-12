import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  FileText, Trash2, Clock, Edit3, Plus, BarChart2,
  BookOpen, CheckCircle2, AlertCircle, Circle,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { listReviews, deleteReview, type ReviewSummary } from '../services/api'

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  draft:       { label: 'Borrador',    color: 'bg-gray-100 text-gray-500',   icon: Circle },
  in_progress: { label: 'En progreso', color: 'bg-blue-100 text-blue-700',   icon: AlertCircle },
  completed:   { label: 'Completado',  color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
}

function StatPill({ label, value }: { label: string; value: string | number }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-gray-400 bg-gray-50 rounded-full px-2 py-0.5">
      {label}: <strong className="text-gray-600">{value}</strong>
    </span>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: reviews = [], isLoading } = useQuery({
    queryKey: ['reviews'],
    queryFn: listReviews,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteReview(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reviews'] })
      toast.success('Revisión eliminada')
    },
    onError: () => toast.error('Error al eliminar la revisión'),
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-full min-h-[40vh]">
      <div className="text-gray-400 text-sm">Cargando revisiones...</div>
    </div>
  )

  const byStatus = {
    completed:   reviews.filter((r: ReviewSummary) => r.status === 'completed').length,
    in_progress: reviews.filter((r: ReviewSummary) => r.status === 'in_progress').length,
    draft:       reviews.filter((r: ReviewSummary) => r.status === 'draft').length,
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Mis Meta-análisis</h2>
          <p className="text-gray-400 text-sm mt-0.5">
            {reviews.length} revisión{reviews.length !== 1 ? 'es' : ''} guardada{reviews.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={() => navigate('/new')}
          className="btn-primary"
        >
          <Plus size={16} /> Nuevo Meta-análisis
        </button>
      </div>

      {/* Summary stats */}
      {reviews.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: 'Completados', count: byStatus.completed, color: 'bg-green-50 border-green-200 text-green-700' },
            { label: 'En progreso', count: byStatus.in_progress, color: 'bg-blue-50 border-blue-200 text-blue-700' },
            { label: 'Borradores',  count: byStatus.draft,       color: 'bg-gray-50 border-gray-200 text-gray-500' },
          ].map(({ label, count, color }) => (
            <div key={label} className={`rounded-xl border p-4 text-center ${color}`}>
              <p className="text-2xl font-bold">{count}</p>
              <p className="text-xs font-medium mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* List */}
      {reviews.length === 0 ? (
        <div className="card p-16 text-center">
          <BookOpen className="mx-auto text-gray-200 mb-4" size={56} strokeWidth={1.5} />
          <p className="text-gray-500 font-semibold text-lg">No hay meta-análisis guardados</p>
          <p className="text-gray-400 text-sm mt-1 mb-6">Comienza creando tu primera revisión sistemática</p>
          <button onClick={() => navigate('/new')} className="btn-primary mx-auto">
            <Plus size={15} /> Crear primer meta-análisis
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {reviews.map((r: ReviewSummary) => {
            const cfg = STATUS_CONFIG[r.status] || STATUS_CONFIG.draft
            const StatusIcon = cfg.icon
            return (
              <div
                key={r.id}
                className="card p-5 flex items-center gap-4 hover:border-cochrane-400 hover:shadow-md transition-all cursor-pointer group"
                onClick={() => navigate(`/reviews/${r.id}`)}
              >
                {/* Icon */}
                <div className="w-11 h-11 rounded-xl bg-cochrane-50 flex items-center justify-center shrink-0 group-hover:bg-cochrane-100 transition-colors">
                  <BarChart2 className="text-cochrane-500" size={22} />
                </div>

                {/* Main info */}
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-900 truncate leading-snug">{r.title}</p>
                  <div className="flex flex-wrap items-center gap-2 mt-1.5">
                    {r.prospero_id && (
                      <StatPill label="PROSPERO" value={r.prospero_id} />
                    )}
                    <StatPill label="Estudios" value={r.study_count} />
                    <span className="inline-flex items-center gap-1 text-xs text-gray-400">
                      <Clock size={10} />
                      {new Date(r.updated_at).toLocaleDateString('es-MX', {
                        day: '2-digit', month: 'short', year: 'numeric',
                      })}
                    </span>
                  </div>
                </div>

                {/* Status badge */}
                <span className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full font-medium shrink-0 ${cfg.color}`}>
                  <StatusIcon size={11} />
                  {cfg.label}
                </span>

                {/* Actions */}
                <div
                  className="flex items-center gap-1 shrink-0"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    onClick={() => navigate(`/reviews/${r.id}`)}
                    className="p-2 text-gray-400 hover:text-cochrane-500 rounded-lg hover:bg-cochrane-50 transition-colors"
                    title="Abrir"
                  >
                    <Edit3 size={15} />
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(`¿Eliminar "${r.title}"? Esta acción no se puede deshacer.`))
                        deleteMutation.mutate(r.id)
                    }}
                    className="p-2 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors"
                    title="Eliminar"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <p className="text-center text-xs text-gray-300 mt-8">
        Todos los datos están guardados en la nube · MetaAnalysis Cochrane Platform
      </p>
    </div>
  )
}
