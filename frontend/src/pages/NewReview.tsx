import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { createReview } from '../services/api'
import { ArrowRight, ArrowLeft } from 'lucide-react'

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
  })

  const mutation = useMutation({
    mutationFn: createReview,
    onSuccess: (review) => {
      toast.success('Review created!')
      navigate(`/reviews/${review.id}`)
    },
    onError: () => toast.error('Failed to create review'),
  })

  const set = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => setForm((f) => ({ ...f, [field]: e.target.value }))

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <button
        onClick={() => navigate('/dashboard')}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-6"
      >
        <ArrowLeft size={16} /> Back
      </button>

      <h2 className="text-2xl font-bold text-gray-900 mb-6">Nueva Revisión Sistemática (New Systematic Review)</h2>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate(form)
        }}
        className="space-y-6"
      >
        <div className="card p-6 space-y-4">
          <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
            Información de la Revisión (Review Information)
          </h3>
          <div>
            <label className="label">Título (Title) *</label>
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
              <label className="label">Diseño de estudios (Study Design)</label>
              <input className="input" value={form.study_design} onChange={set('study_design')} placeholder="ECA, CCT..." />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Medida del efecto (Effect measure)</label>
              <select className="input" value={form.effect_measure} onChange={set('effect_measure')}>
                <option value="OR">OR – Razón de Momios (Odds Ratio)</option>
                <option value="RR">RR – Riesgo Relativo (Risk Ratio)</option>
                <option value="RD">RD – Diferencia de Riesgos (Risk Difference)</option>
                <option value="MD">MD – Diferencia de Medias (Mean Difference)</option>
                <option value="SMD">SMD – DM Estandarizada (Standardised MD)</option>
              </select>
            </div>
            <div>
              <label className="label">Modelo de combinación (Pooling model)</label>
              <select className="input" value={form.model_type} onChange={set('model_type')}>
                <option value="random">Efectos aleatorios (Random-effects DL)</option>
                <option value="fixed">Efectos fijos (Fixed-effects IV)</option>
              </select>
            </div>
          </div>
        </div>

        <div className="card p-6 space-y-4">
          <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">PICO</h3>
          {[
            { field: 'population', label: 'Población (Population - P)', placeholder: 'Ej: Adultos con diabetes tipo 2' },
            { field: 'intervention', label: 'Intervención (Intervention - I)', placeholder: 'Ej: Metformina en monoterapia' },
            { field: 'comparison', label: 'Comparación (Comparison - C)', placeholder: 'Ej: Placebo o sin tratamiento' },
            { field: 'outcomes', label: 'Desenlaces (Outcomes - O)', placeholder: 'Ej: Reducción de HbA1c, eventos adversos' },
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

        <div className="flex justify-end">
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? 'Creando...' : 'Crear Revisión (Create Review)'}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </div>
  )
}
