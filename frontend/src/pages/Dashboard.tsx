import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText, Trash2, Clock, Edit3 } from 'lucide-react'
import toast from 'react-hot-toast'
import { listReviews, deleteReview, type ReviewSummary } from '../services/api'

const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-600',
  in_progress: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador (Draft)',
  in_progress: 'En progreso (In progress)',
  completed: 'Completado (Completed)',
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

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-gray-900">Mis Revisiones (Reviews)</h2>
        <p className="text-gray-500 text-sm mt-1">
          {reviews.length} revisión{reviews.length !== 1 ? 'es' : ''} en total
        </p>
      </div>

      {reviews.length === 0 ? (
        <div className="card p-12 text-center">
          <FileText className="mx-auto text-gray-300 mb-3" size={48} />
          <p className="text-gray-500 font-medium">Aún no hay revisiones</p>
          <p className="text-gray-400 text-sm mt-1">Haz clic en "Nueva Revisión" para comenzar</p>
        </div>
      ) : (
        <div className="space-y-3">
          {reviews.map((r: ReviewSummary) => (
            <div
              key={r.id}
              className="card p-5 flex items-center gap-4 hover:border-cochrane-500 transition-colors cursor-pointer"
              onClick={() => navigate(`/reviews/${r.id}`)}
            >
              <FileText className="text-cochrane-500 shrink-0" size={24} />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900 truncate">{r.title}</p>
                <div className="flex items-center gap-3 mt-1">
                  {r.prospero_id && (
                    <span className="text-xs text-gray-400">PROSPERO: {r.prospero_id}</span>
                  )}
                  <span className="text-xs text-gray-400 flex items-center gap-1">
                    <Clock size={11} />
                    {new Date(r.updated_at).toLocaleDateString()}
                  </span>
                  <span className="text-xs text-gray-400">{r.study_count} estudios</span>
                </div>
              </div>
              <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${STATUS_STYLES[r.status] || STATUS_STYLES.draft}`}>
                {STATUS_LABELS[r.status] || r.status}
              </span>
              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => navigate(`/reviews/${r.id}`)}
                  className="p-2 text-gray-400 hover:text-cochrane-500 rounded-lg hover:bg-cochrane-50 transition-colors"
                  title="Edit"
                >
                  <Edit3 size={16} />
                </button>
                <button
                  onClick={() => {
                    if (confirm('¿Eliminar esta revisión?')) deleteMutation.mutate(r.id)
                  }}
                  className="p-2 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors"
                  title="Delete"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
