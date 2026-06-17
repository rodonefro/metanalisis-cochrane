import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { createReview } from '../services/api'
import { ArrowRight, ArrowLeft, Info, Target, Filter, CheckCircle2 } from 'lucide-react'

const TABS = [
  { id: 'general',   label: 'General',   icon: Info },
  { id: 'pico',      label: 'PICO',      icon: Target },
  { id: 'criteria',  label: 'Criterios de Inclusión / Exclusión', icon: Filter },
]

const STUDY_TYPES = [
  'Ensayo clínico controlado aleatorizado (ECA/RCT)',
  'Ensayo clínico controlado no aleatorizado',
  'Estudio cuasi-experimental',
  'Estudio de cohorte prospectivo',
  'Estudio de cohorte retrospectivo',
  'Estudio de casos y controles',
  'Estudio transversal (corte transversal)',
  'Serie de casos',
  'Revisión sistemática / Meta-análisis',
  'Estudio cualitativo',
]

export default function NewReview() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('general')
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
    types_of_studies: '',
    inclusion_criteria: '',
    exclusion_criteria: '',
    subgroup_study_types: '',
  })

  const mutation = useMutation({
    mutationFn: createReview,
    onSuccess: (review) => {
      toast.success('¡Revisión creada! Agrega estudios y ejecuta el Pipeline IA.')
      navigate(`/reviews/${review.id}`)
    },
    onError: () => toast.error('Error al crear la revisión'),
  })

  const set = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const selectedTypes = form.types_of_studies ? form.types_of_studies.split(', ').filter(Boolean) : []
  const toggleStudyType = (type: string) => {
    setForm((f) => {
      const current = f.types_of_studies ? f.types_of_studies.split(', ').filter(Boolean) : []
      const next = current.includes(type) ? current.filter((t) => t !== type) : [...current, type]
      return { ...f, types_of_studies: next.join(', ') }
    })
  }

  const selectedSubgroupTypes = form.subgroup_study_types ? form.subgroup_study_types.split(', ').filter(Boolean) : []
  const toggleSubgroupStudyType = (type: string) => {
    setForm((f) => {
      const current = f.subgroup_study_types ? f.subgroup_study_types.split(', ').filter(Boolean) : []
      const next = current.includes(type) ? current.filter((t) => t !== type) : [...current, type]
      return { ...f, subgroup_study_types: next.join(', ') }
    })
  }

  const hasCriteria = form.inclusion_criteria.trim() || form.exclusion_criteria.trim()
  const canSubmit = form.title.trim().length > 0

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <button
        onClick={() => navigate('/dashboard')}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-6"
      >
        <ArrowLeft size={16} /> Inicio
      </button>

      <h2 className="text-2xl font-bold text-gray-900 mb-1">Nueva Revisión Sistemática</h2>
      <p className="text-sm text-gray-400 mb-6">
        Completa los campos y define los criterios para que la IA los use al cribar estudios automáticamente.
      </p>

      {/* ── Tabs ── */}
      <div className="flex border-b border-gray-200 mb-6">
        {TABS.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          const hasBadge = tab.id === 'criteria' && !!hasCriteria
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors relative
                ${isActive
                  ? 'border-cochrane-500 text-cochrane-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
            >
              <Icon size={15} />
              {tab.label}
              {hasBadge && (
                <CheckCircle2 size={13} className="text-green-500" />
              )}
            </button>
          )
        })}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!canSubmit) { toast.error('El título es obligatorio'); return }
          mutation.mutate(form)
        }}
        className="space-y-5"
      >
        {/* ── Tab: General ── */}
        {activeTab === 'general' && (
          <div className="card p-6 space-y-4">
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
            <div className="flex justify-end pt-1">
              <button type="button" onClick={() => setActiveTab('pico')} className="btn-primary text-sm">
                Siguiente: PICO <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Tab: PICO ── */}
        {activeTab === 'pico' && (
          <div className="card p-6 space-y-4">
            {[
              { field: 'population',   label: 'Población (P)',    placeholder: 'Ej: Adultos con diabetes tipo 2' },
              { field: 'intervention', label: 'Intervención (I)', placeholder: 'Ej: Metformina en monoterapia' },
              { field: 'comparison',   label: 'Comparación (C)',  placeholder: 'Ej: Placebo o sin tratamiento' },
              { field: 'outcomes',     label: 'Desenlaces (O)',   placeholder: 'Ej: Reducción de HbA1c, eventos adversos' },
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
            <div className="flex justify-between pt-1">
              <button type="button" onClick={() => setActiveTab('general')} className="btn-secondary text-sm">
                <ArrowLeft size={14} /> Atrás
              </button>
              <button type="button" onClick={() => setActiveTab('criteria')} className="btn-primary text-sm">
                Siguiente: Criterios <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Tab: Criterios de Inclusión / Exclusión ── */}
        {activeTab === 'criteria' && (
          <div className="card p-6 space-y-5">
            <div className="bg-cochrane-50 border border-cochrane-100 rounded-lg p-3 text-xs text-cochrane-700">
              La IA usa estos criterios en el <strong>Pipeline Completo</strong> para decidir automáticamente
              qué estudios incluir o excluir al cribar tu biblioteca de referencias.
            </div>

            <div>
              <label className="label">Tipos de estudio a incluir</label>
              <p className="text-xs text-gray-400 mb-2">
                Selecciona todos los diseños que la IA debe aceptar. Si no marcas ninguno, se aceptará cualquier diseño relevante a tu PICO.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {STUDY_TYPES.map((type) => {
                  const checked = selectedTypes.includes(type)
                  return (
                    <label
                      key={type}
                      className={`flex items-start gap-2 text-xs rounded-lg border p-2 cursor-pointer transition-colors
                        ${checked ? 'border-cochrane-400 bg-cochrane-50 text-cochrane-800' : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}
                    >
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={checked}
                        onChange={() => toggleStudyType(type)}
                      />
                      {type}
                    </label>
                  )
                })}
              </div>
            </div>

            <div>
              <label className="label text-green-700 font-semibold">Criterios de Inclusión</label>
              <textarea
                className="input resize-none border-green-300 focus:border-green-500 focus:ring-green-200"
                rows={5}
                value={form.inclusion_criteria}
                onChange={set('inclusion_criteria')}
                placeholder={
                  'Ej:\n• Estudios aleatorizados controlados (ECA)\n• Adultos ≥ 18 años con diagnóstico confirmado\n• Seguimiento ≥ 3 meses\n• Desenlace primario reportado'
                }
              />
            </div>

            <div>
              <label className="label text-red-700 font-semibold">Criterios de Exclusión</label>
              <textarea
                className="input resize-none border-red-300 focus:border-red-500 focus:ring-red-200"
                rows={5}
                value={form.exclusion_criteria}
                onChange={set('exclusion_criteria')}
                placeholder={
                  'Ej:\n• Estudios observacionales o series de casos\n• Población pediátrica (< 18 años)\n• Datos insuficientes para el meta-análisis\n• Publicaciones duplicadas o datos no originales'
                }
              />
            </div>

            {hasCriteria && (
              <div className="flex items-center gap-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg p-2.5">
                <CheckCircle2 size={14} />
                Criterios definidos — la IA los aplicará automáticamente al cribar estudios.
              </div>
            )}

            <div className="pt-2 border-t border-gray-100">
              <label className="label">Tipos de estudio a incluir para un sub-análisis</label>
              <p className="text-xs text-gray-400 mb-2">
                Opcional. Define qué diseños se podrán aislar en un análisis de subgrupos o sensibilidad,
                independiente de los tipos de estudio principales de la revisión.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {STUDY_TYPES.map((type) => {
                  const checked = selectedSubgroupTypes.includes(type)
                  return (
                    <label
                      key={type}
                      className={`flex items-start gap-2 text-xs rounded-lg border p-2 cursor-pointer transition-colors
                        ${checked ? 'border-cochrane-400 bg-cochrane-50 text-cochrane-800' : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}
                    >
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={checked}
                        onChange={() => toggleSubgroupStudyType(type)}
                      />
                      {type}
                    </label>
                  )
                })}
              </div>
            </div>

            <div className="flex justify-between pt-1">
              <button type="button" onClick={() => setActiveTab('pico')} className="btn-secondary text-sm">
                <ArrowLeft size={14} /> Atrás
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={mutation.isPending || !canSubmit}
              >
                {mutation.isPending ? 'Creando...' : 'Crear Revisión'}
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Submit visible from any tab if title filled */}
        {activeTab !== 'criteria' && canSubmit && (
          <div className="flex justify-end">
            <button
              type="submit"
              className="text-sm text-gray-400 hover:text-cochrane-600 underline"
              disabled={mutation.isPending}
            >
              {mutation.isPending ? 'Creando...' : 'Crear revisión ahora (sin completar todos los campos)'}
            </button>
          </div>
        )}
      </form>
    </div>
  )
}
