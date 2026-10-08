import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Library, ChevronDown, ChevronUp, Upload, Download, X, CheckCircle2, XCircle, HelpCircle,
  RotateCcw, Search, ExternalLink, FileText,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  importReferences, exportReferences, setScreeningDecision, listSearches,
  type Study, type SearchSource,
} from '../services/api'

interface Props {
  reviewId: number
  studies: Study[]
}

const KNOWN_SOURCES = [
  'PubMed/MEDLINE', 'Embase', 'Scopus', 'Web of Science', 'Cochrane CENTRAL', 'LILACS', 'SciELO',
  'CINAHL', 'PsycINFO', 'Google Scholar', 'ClinicalTrials.gov', 'WHO ICTRP', 'Elicit IA', 'SciSpace IA',
]

const EXCLUSION_REASONS = [
  'Población incorrecta',
  'Intervención incorrecta',
  'Comparador incorrecto',
  'Desenlace no evaluado',
  'Diseño de estudio incorrecto',
  'Tipo de publicación (revisión, editorial, carta, resumen de congreso)',
  'Estudio en animales o in vitro',
  'Datos insuficientes o no extraíbles',
  'Idioma o fecha fuera de los criterios',
]

type Decision = 'include' | 'exclude' | 'maybe' | null
type Filter = 'all' | 'pending' | 'include' | 'exclude' | 'maybe' | 'not_retrieved'

function decisionOf(s: Study): Decision {
  if (s.screening_decision) return s.screening_decision
  if (!s.screening_reviewed) return null
  if (s.included) return 'include'
  if ((s.exclusion_reason || '').startsWith('Requiere revisión a texto completo')) return 'maybe'
  return 'exclude'
}

const DECISION_STYLE: Record<string, string> = {
  include: 'bg-green-100 text-green-700 border-green-200',
  exclude: 'bg-red-100 text-red-700 border-red-200',
  maybe: 'bg-amber-100 text-amber-700 border-amber-200',
  pending: 'bg-gray-100 text-gray-500 border-gray-200',
}
const DECISION_LABEL: Record<string, string> = {
  include: 'Incluido', exclude: 'Excluido', maybe: 'Quizás', pending: 'Pendiente',
}

function storageGet(key: string): string {
  try { return localStorage.getItem(key) || '' } catch { return '' }
}
function storageSet(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* storage unavailable */ }
}

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function Highlight({ text, include, exclude }: { text: string; include: string[]; exclude: string[] }) {
  const terms = [...include, ...exclude].filter(Boolean)
  if (!terms.length || !text) return <>{text}</>
  const re = new RegExp(`(${terms.map(escapeRe).join('|')})`, 'gi')
  const inc = new Set(include.map(t => t.toLowerCase()))
  return (
    <>
      {text.split(re).map((part, i) => {
        const low = part.toLowerCase()
        if (inc.has(low)) return <mark key={i} className="bg-green-200 text-green-900 rounded px-0.5">{part}</mark>
        if (exclude.some(t => t.toLowerCase() === low)) return <mark key={i} className="bg-red-200 text-red-900 rounded px-0.5">{part}</mark>
        return <span key={i}>{part}</span>
      })}
    </>
  )
}

const splitTerms = (s: string) => s.split(/[,;\n]/).map(t => t.trim()).filter(t => t.length > 1)

export default function ReferenceManager({ reviewId, studies }: Props) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [screening, setScreening] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [meta, setMeta] = useState({
    database_name: '', source_type: 'database', search_string: '', search_date: '', results_count: '',
  })
  const [exportFmt, setExportFmt] = useState<'ris' | 'bib' | 'csv'>('ris')
  const [exportScope, setExportScope] = useState('all')

  const { data: searches = [] } = useQuery({
    queryKey: ['searches', reviewId],
    queryFn: () => listSearches(reviewId),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['review', reviewId] })
    qc.invalidateQueries({ queryKey: ['searches', reviewId] })
  }

  const importMutation = useMutation({
    mutationFn: () => importReferences(reviewId, file!, {
      database_name: meta.database_name.trim(),
      source_type: meta.source_type,
      search_string: meta.search_string || undefined,
      search_date: meta.search_date || undefined,
      results_count: meta.results_count === '' ? undefined : Number(meta.results_count),
    }),
    onSuccess: (res) => {
      toast.success(
        `${res.format.toUpperCase()}: ${res.records} registros leídos · ${res.added} nuevos · ${res.duplicates_merged} duplicados fusionados`,
        { duration: 6000 },
      )
      setFile(null)
      setMeta({ database_name: '', source_type: 'database', search_string: '', search_date: '', results_count: '' })
      invalidate()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al importar referencias'),
  })

  const handleExport = async () => {
    try {
      const blob = await exportReferences(reviewId, exportFmt, exportScope)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `referencias_${exportScope}.${exportFmt}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Error al exportar referencias')
    }
  }

  const counts = useMemo(() => {
    const c = { pending: 0, include: 0, exclude: 0, maybe: 0 }
    studies.forEach(s => { c[(decisionOf(s) || 'pending') as keyof typeof c]++ })
    return c
  }, [studies])

  return (
    <>
      {screening && (
        <ScreeningModal
          reviewId={reviewId}
          studies={studies}
          searches={searches}
          onClose={() => setScreening(false)}
          onChanged={invalidate}
        />
      )}

      <div className="card overflow-hidden">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50"
        >
          <div className="flex items-center gap-2 flex-wrap">
            <Library size={18} className="text-cochrane-500" />
            <span className="font-semibold text-gray-800">Gestor de referencias (Rayyan / Zotero)</span>
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{studies.length} registros</span>
            {counts.pending > 0 && (
              <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">{counts.pending} sin cribar</span>
            )}
          </div>
          {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
        </button>

        {open && (
          <div className="border-t border-gray-100 p-5 space-y-5">
            {/* Status */}
            <div className="flex flex-wrap gap-2 text-xs">
              {(['pending', 'include', 'maybe', 'exclude'] as const).map(k => (
                <span key={k} className={`px-2 py-1 rounded-full border ${DECISION_STYLE[k]}`}>
                  {DECISION_LABEL[k]}: {counts[k]}
                </span>
              ))}
              <button type="button" onClick={() => setScreening(true)} className="btn-primary text-xs ml-auto" disabled={!studies.length}>
                <FileText size={14} /> Abrir cribado (título/resumen y texto completo)
              </button>
            </div>

            {/* Import */}
            <div className="rounded-lg border border-gray-200 p-4 space-y-3">
              <p className="text-sm font-semibold text-gray-700">1. Importar resultados de una búsqueda</p>
              <p className="text-xs text-gray-500">
                Una importación por base de datos. Formatos: RIS (Zotero, EndNote, Mendeley, Rayyan, Scopus, Embase, WoS),
                BibTeX (.bib), PubMed (.nbib / .txt formato MEDLINE), CSV de Rayyan o Excel/CSV propio.
                Los duplicados se fusionan automáticamente por DOI, PMID o título y quedan contados para el PRISMA.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="label">Archivo</label>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".ris,.enw,.bib,.nbib,.txt,.csv,.xlsx,.xls"
                    className="input text-xs"
                    onChange={e => setFile(e.target.files?.[0] || null)}
                  />
                </div>
                <div>
                  <label className="label">Base de datos / fuente *</label>
                  <input
                    className="input text-xs"
                    list="known-sources"
                    placeholder="PubMed/MEDLINE"
                    value={meta.database_name}
                    onChange={e => setMeta(m => ({ ...m, database_name: e.target.value }))}
                  />
                  <datalist id="known-sources">
                    {[...new Set([...searches.map(s => s.database_name), ...KNOWN_SOURCES])].map(n => <option key={n} value={n} />)}
                  </datalist>
                </div>
                <div>
                  <label className="label">Tipo de fuente</label>
                  <select
                    className="input text-xs"
                    value={meta.source_type}
                    onChange={e => setMeta(m => ({ ...m, source_type: e.target.value }))}
                  >
                    <option value="database">Base de datos</option>
                    <option value="register">Registro de ensayos</option>
                    <option value="other">Otros métodos (citas, webs, expertos)</option>
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="label">Fecha de búsqueda</label>
                    <input
                      type="date"
                      className="input text-xs"
                      value={meta.search_date}
                      onChange={e => setMeta(m => ({ ...m, search_date: e.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="label">N reportado por la base</label>
                    <input
                      type="number"
                      min={0}
                      className="input text-xs"
                      placeholder="opcional"
                      value={meta.results_count}
                      onChange={e => setMeta(m => ({ ...m, results_count: e.target.value }))}
                    />
                  </div>
                </div>
                <div className="sm:col-span-2">
                  <label className="label">Estrategia / cadena de búsqueda</label>
                  <textarea
                    className="input text-xs font-mono"
                    rows={2}
                    placeholder='("sepsis"[MeSH] OR septic*) AND ("vitamin C" OR ascorb*)'
                    value={meta.search_string}
                    onChange={e => setMeta(m => ({ ...m, search_string: e.target.value }))}
                  />
                </div>
              </div>
              <button
                type="button"
                className="btn-primary text-xs"
                disabled={!file || !meta.database_name.trim() || importMutation.isPending}
                onClick={() => importMutation.mutate()}
              >
                <Upload size={14} />
                {importMutation.isPending ? 'Importando...' : 'Importar referencias'}
              </button>
            </div>

            {/* Export */}
            <div className="rounded-lg border border-gray-200 p-4 space-y-3">
              <p className="text-sm font-semibold text-gray-700">2. Exportar a Zotero, Rayyan, EndNote o Mendeley</p>
              <div className="flex flex-wrap items-end gap-2">
                <div>
                  <label className="label">Formato</label>
                  <select className="input text-xs" value={exportFmt} onChange={e => setExportFmt(e.target.value as any)}>
                    <option value="ris">RIS (Zotero, EndNote, Mendeley, Rayyan)</option>
                    <option value="bib">BibTeX (Zotero, LaTeX)</option>
                    <option value="csv">CSV formato Rayyan</option>
                  </select>
                </div>
                <div>
                  <label className="label">Registros</label>
                  <select className="input text-xs" value={exportScope} onChange={e => setExportScope(e.target.value)}>
                    <option value="all">Todos</option>
                    <option value="included">Incluidos</option>
                    <option value="excluded">Excluidos</option>
                    <option value="maybe">Quizás</option>
                    <option value="pending">Sin cribar</option>
                  </select>
                </div>
                <button type="button" className="btn-secondary text-xs" onClick={handleExport} disabled={!studies.length}>
                  <Download size={14} /> Exportar
                </button>
              </div>
              <p className="text-[11px] text-gray-400">
                La decisión de cribado y el motivo de exclusión viajan en las notas (N1 en RIS, campo "notes" en Rayyan),
                así que puedes cribar en Rayyan y volver a importar: las decisiones de Rayyan se respetan.
              </p>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

// ── Rayyan-style screening ─────────────────────────────────────────────────────

function ScreeningModal({
  reviewId, studies, searches, onClose, onChanged,
}: {
  reviewId: number
  studies: Study[]
  searches: SearchSource[]
  onClose: () => void
  onChanged: () => void
}) {
  const [filter, setFilter] = useState<Filter>('pending')
  const [query, setQuery] = useState('')
  const kwKey = `refmgr-keywords-${reviewId}`
  const [incTerms, setIncTerms] = useState(() => storageGet(`${kwKey}-inc`))
  const [excTerms, setExcTerms] = useState(() => storageGet(`${kwKey}-exc`))
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const [customReason, setCustomReason] = useState('')
  const [stage, setStage] = useState<'title_abstract' | 'full_text'>('title_abstract')

  useEffect(() => { storageSet(`${kwKey}-inc`, incTerms) }, [incTerms, kwKey])
  useEffect(() => { storageSet(`${kwKey}-exc`, excTerms) }, [excTerms, kwKey])

  const include = splitTerms(incTerms)
  const exclude = splitTerms(excTerms)

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return studies.filter(s => {
      const d = decisionOf(s)
      if (filter === 'pending' && d !== null) return false
      if (filter === 'not_retrieved' && s.full_text_status !== 'not_retrieved') return false
      if (['include', 'exclude', 'maybe'].includes(filter) && d !== filter) return false
      if (q) {
        const hay = `${s.title || ''} ${s.abstract_text || ''} ${s.authors || ''} ${s.journal || ''} ${s.keywords || ''}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [studies, filter, query])

  const selected = studies.find(s => s.id === selectedId) || visible[0] || null
  const idx = selected ? visible.findIndex(s => s.id === selected.id) : -1

  useEffect(() => {
    if (selected) {
      setStage(selected.screening_stage || (selected.full_text_status ? 'full_text' : 'title_abstract'))
    }
  }, [selected?.id])  // eslint-disable-line react-hooks/exhaustive-deps

  const decide = useMutation({
    mutationFn: (data: Parameters<typeof setScreeningDecision>[2]) => setScreeningDecision(reviewId, selected!.id, data),
    onSuccess: () => onChanged(),
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al guardar la decisión'),
  })

  const goNext = () => {
    if (idx >= 0 && idx < visible.length - 1) setSelectedId(visible[idx + 1].id)
  }

  const apply = (decision: Decision) => {
    if (!selected) return
    const finalReason = reason === '__other' ? customReason.trim() : reason
    if (decision === 'exclude' && !finalReason) {
      toast.error('Elige el motivo de exclusión (lo exige PRISMA)')
      return
    }
    decide.mutate({
      decision,
      stage,
      reason: decision === 'exclude' ? finalReason : decision === 'maybe' ? 'Requiere revisión a texto completo' : null,
    })
    // In the "pending" view the record leaves the list; elsewhere move on.
    if (filter !== 'pending') goNext()
    else if (idx >= 0 && visible[idx + 1]) setSelectedId(visible[idx + 1].id)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'Escape') onClose()
      else if (e.key === 'i' || e.key === 'I') apply('include')
      else if (e.key === 'e' || e.key === 'E') apply('exclude')
      else if (e.key === 'm' || e.key === 'M') apply('maybe')
      else if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); goNext() }
      else if (e.key === 'ArrowUp' || e.key === 'k') {
        e.preventDefault()
        if (idx > 0) setSelectedId(visible[idx - 1].id)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const evidence = useMemo(() => {
    try { return selected?.extraction_evidence ? JSON.parse(selected.extraction_evidence) : null } catch { return null }
  }, [selected?.extraction_evidence])

  const FILTERS: [Filter, string][] = [
    ['pending', 'Pendientes'], ['include', 'Incluidos'], ['maybe', 'Quizás'], ['exclude', 'Excluidos'],
    ['not_retrieved', 'No recuperados'], ['all', 'Todos'],
  ]

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-stretch justify-center p-2 sm:p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-7xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 flex-wrap">
          <span className="font-semibold text-gray-800">Cribado de referencias</span>
          <div className="flex gap-1 flex-wrap">
            {FILTERS.map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => { setFilter(k); setSelectedId(null) }}
                className={`text-xs px-2 py-1 rounded-full border ${filter === k ? 'bg-cochrane-500 text-white border-cochrane-500' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="relative ml-auto">
            <Search size={14} className="absolute left-2 top-2 text-gray-400" />
            <input
              className="input text-xs pl-7 py-1.5 w-56"
              placeholder="Buscar en título/resumen..."
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </div>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-700" title="Cerrar (Esc)">
            <X size={20} />
          </button>
        </div>

        {/* Keyword highlighting */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 px-4 py-2 bg-gray-50 border-b border-gray-200">
          <input
            className="input text-xs"
            placeholder="Palabras para incluir (verde), separadas por coma: randomized, sepsis..."
            value={incTerms}
            onChange={e => setIncTerms(e.target.value)}
          />
          <input
            className="input text-xs"
            placeholder="Palabras para excluir (rojo): rats, review, pediatric..."
            value={excTerms}
            onChange={e => setExcTerms(e.target.value)}
          />
        </div>

        <div className="flex-1 flex min-h-0 flex-col md:flex-row">
          {/* List */}
          <div className="md:w-80 border-b md:border-b-0 md:border-r border-gray-200 overflow-y-auto max-h-48 md:max-h-none">
            {visible.length === 0 && (
              <p className="p-4 text-xs text-gray-400">No hay registros en esta vista.</p>
            )}
            {visible.map(s => {
              const d = decisionOf(s) || 'pending'
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSelectedId(s.id)}
                  className={`w-full text-left px-3 py-2 border-b border-gray-100 hover:bg-gray-50 ${selected?.id === s.id ? 'bg-cochrane-50' : ''}`}
                >
                  <p className="text-xs font-medium text-gray-800 line-clamp-2">{s.title || s.study_label || '(sin título)'}</p>
                  <div className="flex items-center gap-1 mt-1">
                    <span className={`text-[10px] px-1.5 rounded border ${DECISION_STYLE[d]}`}>{DECISION_LABEL[d]}</span>
                    <span className="text-[10px] text-gray-400 truncate">{s.study_label}</span>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Detail */}
          <div className="flex-1 overflow-y-auto p-5">
            {!selected ? (
              <p className="text-sm text-gray-400">Selecciona un registro.</p>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <span>{idx + 1} de {visible.length}</span>
                  <span className={`px-1.5 rounded border ${DECISION_STYLE[decisionOf(selected) || 'pending']}`}>
                    {DECISION_LABEL[decisionOf(selected) || 'pending']}
                  </span>
                  {selected.exclusion_reason && decisionOf(selected) !== 'include' && (
                    <span className="text-red-500 truncate">· {selected.exclusion_reason}</span>
                  )}
                </div>
                <h2 className="text-base font-semibold text-gray-900 leading-snug">
                  <Highlight text={selected.title || '(sin título)'} include={include} exclude={exclude} />
                </h2>
                <p className="text-xs text-gray-600">{selected.authors || 'Autores no disponibles'}</p>
                <p className="text-xs text-gray-500">
                  {[selected.journal, selected.year, selected.volume && `${selected.volume}${selected.issue ? `(${selected.issue})` : ''}`,
                    selected.first_page && `${selected.first_page}${selected.last_page ? `-${selected.last_page}` : ''}`]
                    .filter(Boolean).join(' · ')}
                </p>
                <div className="flex flex-wrap gap-2 text-xs">
                  {selected.doi && (
                    <a href={`https://doi.org/${selected.doi}`} target="_blank" rel="noreferrer" className="text-cochrane-600 hover:underline inline-flex items-center gap-1">
                      DOI {selected.doi} <ExternalLink size={11} />
                    </a>
                  )}
                  {selected.pmid && (
                    <a href={`https://pubmed.ncbi.nlm.nih.gov/${selected.pmid}/`} target="_blank" rel="noreferrer" className="text-cochrane-600 hover:underline inline-flex items-center gap-1">
                      PMID {selected.pmid} <ExternalLink size={11} />
                    </a>
                  )}
                  {(selected.all_sources || selected.source_database || '').split(';').filter(x => x.trim()).map(src => (
                    <span key={src} className="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-100">{src.trim()}</span>
                  ))}
                  {!(selected.all_sources || selected.source_database) && (
                    <select
                      className="input text-xs py-0.5 w-auto border-amber-300"
                      value=""
                      onChange={e => e.target.value && decide.mutate({ source_database: e.target.value })}
                      title="Este registro no tiene base de datos de origen; asígnala para que el PRISMA cuadre"
                    >
                      <option value="">Asignar fuente…</option>
                      {searches.map(s => <option key={s.id} value={s.database_name}>{s.database_name}</option>)}
                    </select>
                  )}
                </div>

                <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-line bg-gray-50 rounded-lg p-4">
                  {selected.abstract_text
                    ? <Highlight text={selected.abstract_text} include={include} exclude={exclude} />
                    : <span className="text-gray-400 italic">Sin resumen disponible.</span>}
                </div>
                {selected.keywords && (
                  <p className="text-xs text-gray-500"><span className="font-semibold">Palabras clave:</span> {selected.keywords}</p>
                )}

                {evidence && Object.keys(evidence).length > 0 && (
                  <div className="rounded-lg border border-green-200 bg-green-50 p-3">
                    <p className="text-xs font-semibold text-green-800 mb-1">Datos extraídos con su cita de origen</p>
                    <ul className="space-y-1">
                      {Object.entries(evidence).map(([field, ev]: [string, any]) => (
                        <li key={field} className="text-xs text-green-900">
                          <span className="font-mono">{field} = {ev.value}</span>
                          <span className="text-green-700"> — “{ev.quote}”</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Decision controls */}
                <div className="rounded-lg border border-gray-200 p-4 space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="label">Fase de la decisión</label>
                      <select className="input text-xs" value={stage} onChange={e => setStage(e.target.value as any)}>
                        <option value="title_abstract">Cribado de título y resumen</option>
                        <option value="full_text">Evaluación a texto completo</option>
                      </select>
                    </div>
                    <div>
                      <label className="label">Texto completo</label>
                      <select
                        className="input text-xs"
                        value={selected.full_text_status || ''}
                        onChange={e => decide.mutate({ full_text_status: (e.target.value || '') as any })}
                      >
                        <option value="">No buscado todavía</option>
                        <option value="retrieved">Recuperado</option>
                        <option value="not_retrieved">No se pudo recuperar</option>
                      </select>
                    </div>
                    <div className="sm:col-span-2">
                      <label className="label">Motivo de exclusión</label>
                      <select className="input text-xs" value={reason} onChange={e => setReason(e.target.value)}>
                        <option value="">— elegir —</option>
                        {EXCLUSION_REASONS.map(r => <option key={r} value={r}>{r}</option>)}
                        <option value="__other">Otro (escribir)</option>
                      </select>
                      {reason === '__other' && (
                        <input
                          className="input text-xs mt-2"
                          placeholder="Motivo de exclusión"
                          value={customReason}
                          onChange={e => setCustomReason(e.target.value)}
                        />
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => apply('include')} disabled={decide.isPending}
                      className="inline-flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700">
                      <CheckCircle2 size={16} /> Incluir <kbd className="text-[10px] opacity-70">I</kbd>
                    </button>
                    <button type="button" onClick={() => apply('maybe')} disabled={decide.isPending}
                      className="inline-flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-medium bg-amber-500 text-white hover:bg-amber-600">
                      <HelpCircle size={16} /> Quizás <kbd className="text-[10px] opacity-70">M</kbd>
                    </button>
                    <button type="button" onClick={() => apply('exclude')} disabled={decide.isPending}
                      className="inline-flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700">
                      <XCircle size={16} /> Excluir <kbd className="text-[10px] opacity-70">E</kbd>
                    </button>
                    {decisionOf(selected) && (
                      <button type="button" onClick={() => decide.mutate({ decision: null })} disabled={decide.isPending}
                        className="btn-secondary text-xs">
                        <RotateCcw size={14} /> Deshacer decisión
                      </button>
                    )}
                  </div>
                  <p className="text-[11px] text-gray-400">
                    Atajos: I incluir · M quizás · E excluir · ↑/↓ navegar · Esc cerrar. Las exclusiones en la fase de
                    texto completo aparecen con su motivo en el diagrama PRISMA.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
