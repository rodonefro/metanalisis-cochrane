import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { createReview } from '../services/api'
import { ArrowRight, ArrowLeft, CheckCircle2 } from 'lucide-react'

export default function NewReview() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    title: '',
    prospero_id: '',
    effect_measure: 'OR',
    model_type: 'random',
    population: '',
    intervention: '',
    comparison: '',
    outcomes: '',
    study_design: '',
    inclusion_criteria: '',
    exclusion_criteria: '',
  })

  const mutation = useMutation({
    mutationFn: createReview,
    onSuccess: (review) => {
      toast.success('¡Revisión creada! Ahora agrega estudios y ejecuta el Pipeline IA.')
      navigate(`/reviews/${review.id}`)
    },
    onError: () => toast.error('Error al crear la revisión'),
  })

  const set = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const hasCriteria = form.inclusion_criteria.trim() || form.exclusion_criteria.trim()

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <button
        onClick={() => navigate('/dashboard')}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-6"
      >
        <ArrowLeft size={16} /> Inicio
      </button>

      <h2 className="text-2xl font-bold text-gray-900 mb-2">Nueva Revisión Sistemática</h2>
      <p className="text-sm text-gray-500 mb-6">
        Completa la información básica y los criterios de selección. Una vez creada, podrás
        agregar estudios y ejecutar el <strong>Pipeline IA Completo</strong> con un solo clic.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate(form)
        }}
        className="space-y-6"
      >
        {/* ── Información general ── */}
        <div className="card p-6 space-y-4">
          <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
            Información de la Revisión
          </h3>
          <div>
            <label className="label">Título *</label>
            <input
              className="input"
              required
              value={form.title}
              onChange={set('title')}
              placeholder="Ej: Efecto de X intervención sobre Y desenlace en Z población"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">ID PROSPERO</label>
              <input className="input" value={form.prospero_id} onChange={set('prospero_id')} placeholder="CRD42024..." />
            </div>
            <div>
              <label className="label">Diseño de estudios</label>
              <input className="input" value={form.study_design} onChange={set('study_design')} placeholder="ECA, CCT..." />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Medida del efecto</label>
              <select className="input" value={form.effect_measure} onChange={set('effect_measure')}>
                <option value="OR">OR – Odds Ratio</option>
                <option value="RR">RR – Riesgo Relativo</option>
                <option value="RD">RD – Diferencia de Riesgos</option>
                <option value="MD">MD – Diferencia de Medias</option>
                <option value="SMD">SMD – DM Estandarizada</option>
              </select>
            </div>
            <div>
              <label className="label">Modelo de combinación</label>
              <select className="input" value={form.model_type} onChange={set('model_type')}>
                <option value="random">Efectos aleatorios (DL)</option>
                <option value="fixed">Efectos fijos (IV)</option>
              </select>
            </div>
          </div>
        </div>

        {/* ── PICO ── */}
        <div className="card p-6 space-y-4">
          <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">PICO</h3>
          {[
            { field: 'population',    label: 'Población (P)',     placeholder: 'Ej: Adultos con diabetes tipo 2' },
            { field: 'intervention',  label: 'Intervención (I)',  placeholder: 'Ej: Metformina en monoterapia' },
            { field: 'comparison',    label: 'Comparación (C)',   placeholder: 'Ej: Placebo o sin tratamiento' },
            { field: 'outcomes',      label: 'Desenlaces (O)',    placeholder: 'Ej: Reducción de HbA1c, eventos adversos' },
          ].map(({ field, label, placeholder }) => (
            <div key={field}>
              <label className="label">{label}</label>
              <textarea
                className="input resize-none"
                rows={2}
                value={(form as any)[field]}
                onChange={set(field)}
                placeholder={placeholder}
              />
            </div>
          ))}
        </div>

        {/* ── Criterios de selección ── */}
        <div className="card p-6 space-y-4 border-cochrane-200 border-2">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-cochrane-700 text-sm uppercase tracking-wide">
              Criterios de Selección de Estudios
            </h3>
            {hasCriteria && (
              <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                <CheckCircle2 size={13} /> Definidos
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500">
            La IA usará estos criterios para cribar automáticamente los estudios al ejecutar el Pipeline.
          </p>

          <div>
            <label className="label text-green-700">Criterios de Inclusión</label>
            <textarea
              className="input resize-none border-green-200 focus:border-green-400 focus:ring-green-200"
              rows={4}
              value={form.inclusion_criteria}
              onChange={set('inclusion_criteria')}
              placeholder={
                'Ej:\n• Estudios aleatorizados controlados (ECA)\n• Adultos ≥ 18 años con diagnóstico confirmado\n• Seguimiento ≥ 3 meses\n• Desenlace primario reportado (HbA1c o glucosa en ayunas)'
              }
            />
          </div>

          <div>
            <label className="label text-red-700">Criterios de Exclusión</label>
            <textarea
              className="input resize-none border-red-200 focus:border-red-400 focus:ring-red-200"
              rows={4}
              value={form.exclusion_criteria}
              onChange={set('exclusion_criteria')}
              placeholder={
                'Ej:\n• Estudios observacionales, series de casos o reportes de caso\n• Población pediátrica (< 18 años)\n• Datos insuficientes para el meta-análisis\n• Publicaciones duplicadas o datos no originales'
              }
            />
          </div>

          {hasCriteria && (
            <div className="bg-cochrane-50 border border-cochrane-100 rounded-lg p-3 text-xs text-cochrane-700">
              ✓ Criterios guardados. Al crear la revisión y agregar estudios, ejecuta el
              <strong> Pipeline IA Completo</strong> desde el panel de Análisis Estadístico
              para que la IA criba, extraiga y analice automáticamente.
            </div>
          )}
        </div>

        <div className="flex justify-end">
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? 'Creando...' : 'Crear Revisión'}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </div>
  )
}
