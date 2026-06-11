import { useState } from 'react'
import { X, Download, Search, Trash2, ExternalLink } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { deleteStudy, API_BASE, type Study } from '../services/api'

type StudyExtended = Study

const ROB_BADGE: Record<string, string> = {
  low:           'bg-green-100 text-green-700 border border-green-200',
  some_concerns: 'bg-yellow-100 text-yellow-700 border border-yellow-200',
  high:          'bg-red-100 text-red-700 border border-red-200',
}
const ROB_LABEL: Record<string, string> = {
  low: 'Bajo', some_concerns: 'Algunas', high: 'Alto',
}
const ROB_DOMAINS = [
  { key: 'rob_random_sequence',        short: 'Seq.' },
  { key: 'rob_allocation_concealment', short: 'Ocult.' },
  { key: 'rob_blinding_participants',  short: 'Ceg.P' },
  { key: 'rob_blinding_outcome',       short: 'Ceg.E' },
  { key: 'rob_incomplete_data',        short: 'Dat.' },
  { key: 'rob_selective_reporting',    short: 'Rep.' },
  { key: 'rob_other',                  short: 'Otros' },
  { key: 'rob_overall',                short: 'Global' },
]

const TABS = [
  { key: 'biblio',     label: 'Bibliografía (Bibliographic)' },
  { key: 'clinical',   label: 'Clínico (Clinical)' },
  { key: 'extraction', label: 'Extracción (Data Extraction)' },
  { key: 'binary',     label: 'Datos binarios (Binary)' },
  { key: 'continuous', label: 'Datos continuos (Continuous)' },
  { key: 'rob',        label: 'Riesgo de sesgo (RoB)' },
]

interface Props {
  reviewId: number
  studies: StudyExtended[]
  onClose: () => void
}

function RobCell({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-gray-300">—</span>
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${ROB_BADGE[value] || ''}`}>
      {ROB_LABEL[value] || value}
    </span>
  )
}

function TextCell({ value, maxW = 'max-w-[200px]' }: { value: string | null | undefined; maxW?: string }) {
  if (!value) return <span className="text-gray-300">—</span>
  return (
    <span className={`block truncate ${maxW}`} title={value}>{value}</span>
  )
}

function exportCsv(studies: StudyExtended[]) {
  const cols: (keyof StudyExtended)[] = [
    'study_label','authors','year','title','journal','publication_type',
    'volume','issue','doi','abstract_text','first_page','last_page','url',
    'study_design','sample_size',
    'events_intervention','total_intervention','events_control','total_control',
    'mean_intervention','sd_intervention','n_intervention',
    'mean_control','sd_control','n_control',
    'effect_size','effect_size_lower','effect_size_upper',
    'patient_population','group_comparison','survival_outcomes','mortality_factors',
    'key_findings','reasoning_study_design','source_database',
    'objective_text','methods_used','study_results','findings',
    'insights','practical_implications','research_gap',
    'rob_random_sequence','rob_allocation_concealment','rob_blinding_participants',
    'rob_blinding_outcome','rob_incomplete_data','rob_selective_reporting',
    'rob_other','rob_overall','notes',
  ]
  const header = cols.join(',')
  const rows = studies.map(s =>
    cols.map(c => {
      const v = s[c]
      if (v == null) return ''
      const str = String(v)
      return str.includes(',') || str.includes('\n') ? `"${str.replace(/"/g, '""')}"` : str
    }).join(',')
  )
  const csv = [header, ...rows].join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'estudios_metaanalisis.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export default function StudiesDatabaseModal({ reviewId, studies, onClose }: Props) {
  const [tab, setTab] = useState('biblio')
  const [search, setSearch] = useState('')
  const qc = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteStudy(reviewId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['review', reviewId] })
      toast.success('Estudio eliminado')
    },
    onError: () => toast.error('Error al eliminar'),
  })

  const filtered = studies.filter(s => {
    if (!search) return true
    const q = search.toLowerCase()
    const ext = s as StudyExtended
    return (
      (s.study_label || '').toLowerCase().includes(q) ||
      (s.authors || '').toLowerCase().includes(q) ||
      (s.title || '').toLowerCase().includes(q) ||
      (s.journal || '').toLowerCase().includes(q) ||
      (ext.doi || '').toLowerCase().includes(q) ||
      String(s.year || '').includes(q)
    )
  })

  const handleDelete = (s: StudyExtended) => {
    if (confirm(`¿Eliminar "${s.study_label || s.authors || 'este estudio'}"?`))
      deleteMutation.mutate(s.id)
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-white">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white shadow-sm flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Base de datos de estudios (Studies Database)</h2>
          <p className="text-xs text-gray-400 mt-0.5">{filtered.length} de {studies.length} estudios</p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={`${API_BASE}/static/plantilla_estudios.xlsx`}
            download="PLANTILLA_ESTUDIOS.xlsx"
            className="btn-secondary text-xs"
          >
            <Download size={13} /> Plantilla Excel
          </a>
          <button type="button" onClick={() => exportCsv(filtered)} className="btn-secondary text-xs">
            <Download size={13} /> Exportar CSV
          </button>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500">
            <X size={20} />
          </button>
        </div>
      </div>

      {/* ── Search + Tabs ── */}
      <div className="px-6 pt-3 pb-0 border-b border-gray-200 bg-white flex-shrink-0">
        <div className="mb-3 max-w-xs relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input pl-9 text-sm"
            placeholder="Buscar por autor, título, DOI, año..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-0 overflow-x-auto">
          {TABS.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap flex-shrink-0 ${
                tab === t.key
                  ? 'border-cochrane-500 text-cochrane-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Table ── */}
      <div className="flex-1 overflow-auto">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            Sin estudios que mostrar
          </div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead className="bg-gray-50 sticky top-0 z-10">
              {/* ── Bibliographic tab ── */}
              {tab === 'biblio' && (
                <tr>
                  {['Tipo','Título','Autores','Año','Revista','Vol.','Núm.','Pp.','DOI / URL',''].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              )}
              {/* ── Clinical tab ── */}
              {tab === 'clinical' && (
                <tr>
                  {['Estudio','Año','BD fuente','Diseño','Pobl. pacientes','Comparación grupos','Outcomes supervivencia','Factores mortalidad','Hallazgos clave','Razonamiento diseño',''].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              )}
              {/* ── Extraction tab ── */}
              {tab === 'extraction' && (
                <tr>
                  {['Estudio','Año','Objetivo','Métodos','Resultados','Hallazgos','Insights','Implicaciones','Brecha',''].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              )}
              {tab === 'binary' && (
                <tr>
                  {['Estudio','Año','Eventos I','Total I','Tasa I%','Eventos C','Total C','Tasa C%',''].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              )}
              {tab === 'continuous' && (
                <tr>
                  {['Estudio','Año','Media I','DE I','N I','Media C','DE C','N C','Efecto precalc.',''].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              )}
              {tab === 'rob' && (
                <tr>
                  <th className="px-3 py-2 text-left font-semibold text-gray-600 border-b border-gray-200">Estudio</th>
                  <th className="px-3 py-2 text-left font-semibold text-gray-600 border-b border-gray-200">Año</th>
                  {ROB_DOMAINS.map(d => (
                    <th key={d.key} className="px-2 py-2 text-center font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap" title={d.key}>
                      {d.short}
                    </th>
                  ))}
                  <th className="px-3 py-2 border-b border-gray-200"></th>
                </tr>
              )}
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(s => {
                const ext = s as StudyExtended
                return (
                  <tr key={s.id} className="hover:bg-blue-50/30 group">
                    {/* ── Bibliographic ── */}
                    {tab === 'biblio' && (
                      <>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{ext.publication_type || '—'}</td>
                        <td className="px-3 py-2 max-w-[220px]">
                          <TextCell value={s.title} maxW="max-w-[210px]" />
                          {s.study_label && <span className="text-gray-400 text-[10px]">{s.study_label}</span>}
                        </td>
                        <td className="px-3 py-2 max-w-[160px]"><TextCell value={s.authors} maxW="max-w-[150px]" /></td>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{s.year || '—'}</td>
                        <td className="px-3 py-2 max-w-[150px]"><TextCell value={s.journal} maxW="max-w-[140px]" /></td>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{ext.volume || '—'}</td>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{ext.issue || '—'}</td>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">
                          {ext.first_page && ext.last_page ? `${ext.first_page}–${ext.last_page}` : ext.first_page || '—'}
                        </td>
                        <td className="px-3 py-2 max-w-[180px]">
                          {ext.doi ? (
                            <a
                              href={`https://doi.org/${ext.doi}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-cochrane-600 hover:underline flex items-center gap-0.5 truncate max-w-[170px]"
                              title={ext.doi}
                            >
                              <ExternalLink size={10} className="flex-shrink-0" />
                              <span className="truncate">{ext.doi}</span>
                            </a>
                          ) : ext.url ? (
                            <a href={ext.url} target="_blank" rel="noopener noreferrer"
                               className="text-cochrane-600 hover:underline flex items-center gap-0.5 truncate max-w-[170px]">
                              <ExternalLink size={10} className="flex-shrink-0" /> URL
                            </a>
                          ) : '—'}
                        </td>
                      </>
                    )}
                    {/* ── Clinical ── */}
                    {tab === 'clinical' && (
                      <>
                        <td className="px-3 py-2 font-medium max-w-[130px]">
                          <TextCell value={s.study_label || s.authors} maxW="max-w-[120px]" />
                        </td>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{s.year || '—'}</td>
                        <td className="px-3 py-2 max-w-[120px]">
                          <TextCell value={ext.source_database} maxW="max-w-[110px]" />
                        </td>
                        <td className="px-3 py-2 max-w-[100px]">
                          <TextCell value={s.study_design} maxW="max-w-[90px]" />
                        </td>
                        <td className="px-3 py-2 max-w-[160px]">
                          <TextCell value={ext.patient_population} maxW="max-w-[150px]" />
                        </td>
                        <td className="px-3 py-2 max-w-[160px]">
                          <TextCell value={ext.group_comparison} maxW="max-w-[150px]" />
                        </td>
                        <td className="px-3 py-2 max-w-[160px]">
                          <TextCell value={ext.survival_outcomes} maxW="max-w-[150px]" />
                        </td>
                        <td className="px-3 py-2 max-w-[160px]">
                          <TextCell value={ext.mortality_factors} maxW="max-w-[150px]" />
                        </td>
                        <td className="px-3 py-2 max-w-[160px]">
                          <TextCell value={ext.key_findings} maxW="max-w-[150px]" />
                        </td>
                        <td className="px-3 py-2 max-w-[160px]">
                          <TextCell value={ext.reasoning_study_design} maxW="max-w-[150px]" />
                        </td>
                      </>
                    )}
                    {/* ── Extraction ── */}
                    {tab === 'extraction' && (
                      <>
                        <td className="px-3 py-2 font-medium max-w-[130px]">
                          <TextCell value={s.study_label || s.authors} maxW="max-w-[120px]" />
                        </td>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{s.year || '—'}</td>
                        <td className="px-3 py-2 max-w-[160px]"><TextCell value={ext.objective_text} maxW="max-w-[150px]" /></td>
                        <td className="px-3 py-2 max-w-[160px]"><TextCell value={ext.methods_used} maxW="max-w-[150px]" /></td>
                        <td className="px-3 py-2 max-w-[160px]"><TextCell value={ext.study_results} maxW="max-w-[150px]" /></td>
                        <td className="px-3 py-2 max-w-[160px]"><TextCell value={ext.findings} maxW="max-w-[150px]" /></td>
                        <td className="px-3 py-2 max-w-[140px]"><TextCell value={ext.insights} maxW="max-w-[130px]" /></td>
                        <td className="px-3 py-2 max-w-[140px]"><TextCell value={ext.practical_implications} maxW="max-w-[130px]" /></td>
                        <td className="px-3 py-2 max-w-[140px]"><TextCell value={ext.research_gap} maxW="max-w-[130px]" /></td>
                      </>
                    )}
                    {/* ── Binary ── */}
                    {tab === 'binary' && (
                      <>
                        <td className="px-3 py-2 font-medium max-w-[130px]">
                          <TextCell value={s.study_label || s.authors} maxW="max-w-[120px]" />
                        </td>
                        <td className="px-3 py-2 text-gray-500">{s.year || '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-700">{s.events_intervention ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-700">{s.total_intervention ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-500">
                          {s.events_intervention != null && s.total_intervention
                            ? ((s.events_intervention / s.total_intervention) * 100).toFixed(1) + '%' : '—'}
                        </td>
                        <td className="px-3 py-2 text-right text-gray-700">{s.events_control ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-700">{s.total_control ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-500">
                          {s.events_control != null && s.total_control
                            ? ((s.events_control / s.total_control) * 100).toFixed(1) + '%' : '—'}
                        </td>
                      </>
                    )}
                    {/* ── Continuous ── */}
                    {tab === 'continuous' && (
                      <>
                        <td className="px-3 py-2 font-medium max-w-[130px]">
                          <TextCell value={s.study_label || s.authors} maxW="max-w-[120px]" />
                        </td>
                        <td className="px-3 py-2 text-gray-500">{s.year || '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-700">{s.mean_intervention?.toFixed(2) ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-500">{s.sd_intervention?.toFixed(2) ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-500">{s.n_intervention ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-700">{s.mean_control?.toFixed(2) ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-500">{s.sd_control?.toFixed(2) ?? '—'}</td>
                        <td className="px-3 py-2 text-right text-gray-500">{s.n_control ?? '—'}</td>
                        <td className="px-3 py-2 text-gray-500">
                          {s.effect_size != null
                            ? `${s.effect_size.toFixed(3)} [${s.effect_size_lower?.toFixed(3)}, ${s.effect_size_upper?.toFixed(3)}]`
                            : '—'}
                        </td>
                      </>
                    )}
                    {/* ── RoB ── */}
                    {tab === 'rob' && (
                      <>
                        <td className="px-3 py-2 font-medium max-w-[130px]">
                          <TextCell value={s.study_label || s.authors} maxW="max-w-[120px]" />
                        </td>
                        <td className="px-3 py-2 text-gray-500">{s.year || '—'}</td>
                        {ROB_DOMAINS.map(d => (
                          <td key={d.key} className="px-2 py-2 text-center">
                            <RobCell value={(s as any)[d.key]} />
                          </td>
                        ))}
                      </>
                    )}
                    {/* Delete — always last */}
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => handleDelete(ext)}
                        className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition-all"
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Footer ── */}
      <div className="px-6 py-3 border-t border-gray-100 bg-gray-50 flex-shrink-0 flex items-center justify-between">
        <p className="text-xs text-gray-400">
          {filtered.length} estudio(s) · Pasa el cursor sobre una fila para eliminar
        </p>
        <button type="button" onClick={onClose} className="btn-secondary text-xs">
          Cerrar (Close)
        </button>
      </div>
    </div>
  )
}
