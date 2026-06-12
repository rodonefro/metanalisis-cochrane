import { useState, useRef } from 'react'
import { Upload, Plus, Trash2, ChevronDown, ChevronUp, Database, Download, Merge, Wand2, CheckCircle2, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  deleteStudy, uploadStudies, createStudy, mergeStudyDatabases, aiScreenStudies, updateStudy, API_BASE,
  type Study,
} from '../services/api'
import StudiesDatabaseModal from './StudiesDatabaseModal'

const ROB_COLORS: Record<string, string> = {
  low: 'bg-green-100 text-green-700',
  some_concerns: 'bg-yellow-100 text-yellow-700',
  high: 'bg-red-100 text-red-700',
}

interface Props {
  reviewId: number
  studies: Study[]
}

export default function StudiesTable({ reviewId, studies }: Props) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const mergeRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [addingNew, setAddingNew] = useState(false)
  const [showDb, setShowDb] = useState(false)
  const [newStudy, setNewStudy] = useState<Partial<Study>>({ included: true })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['review', reviewId] })
  }

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadStudies(reviewId, file),
    onSuccess: (res: any) => {
      toast.success(`${res.created} estudio(s) importado(s)`)
      invalidate()
      setOpen(true)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al importar archivo'),
  })

  const mergeMutation = useMutation({
    mutationFn: (files: File[]) => mergeStudyDatabases(reviewId, files),
    onSuccess: (res) => {
      const parts = [`+${res.added} nuevos`, `${res.merged} enriquecidos`, `${res.skipped_exact_duplicates} duplicados exactos`]
      toast.success(`Fusión: ${parts.join(' · ')}`)
      if (res.errors?.length) toast.error(`Errores: ${res.errors.join('; ')}`)
      invalidate()
      setOpen(true)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error al fusionar archivos'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteStudy(reviewId, id),
    onSuccess: () => { invalidate(); toast.success('Estudio eliminado') },
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<Study>) => createStudy(reviewId, data),
    onSuccess: () => {
      invalidate()
      setAddingNew(false)
      setNewStudy({ included: true })
      toast.success('Estudio agregado')
    },
    onError: () => toast.error('Error al agregar estudio'),
  })

  const screenMutation = useMutation({
    mutationFn: () => aiScreenStudies(reviewId),
    onSuccess: (res) => {
      toast.success(res.message)
      invalidate()
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error en cribado IA'),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, included }: { id: number; included: boolean }) =>
      updateStudy(reviewId, id, { included }),
    onSuccess: () => invalidate(),
    onError: () => toast.error('Error al cambiar inclusión'),
  })

  const setField = (field: keyof Study) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => setNewStudy((s) => ({ ...s, [field]: e.target.value }))

  return (
    <>
      {showDb && (
        <StudiesDatabaseModal
          reviewId={reviewId}
          studies={studies}
          onClose={() => setShowDb(false)}
        />
      )}

      <div className="card overflow-hidden">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50"
        >
          <div className="flex items-center gap-2">
            <span className="font-semibold text-gray-800">Estudios (Studies)</span>
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
              {studies.filter(s => s.included !== false).length} incluidos
            </span>
            {studies.some(s => s.included === false) && (
              <span className="text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full">
                {studies.filter(s => s.included === false).length} excluidos
              </span>
            )}
          </div>
          {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
        </button>

        {open && (
          <div className="border-t border-gray-100">
            {/* Actions bar */}
            <div className="flex items-center gap-2 px-5 py-3 bg-gray-50 border-b border-gray-100 flex-wrap">
              <input
                type="file"
                ref={fileRef}
                className="hidden"
                accept=".csv,.xlsx,.xls"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) uploadMutation.mutate(file)
                  e.target.value = ''
                }}
              />
              <input
                type="file"
                ref={mergeRef}
                className="hidden"
                accept=".csv,.xlsx,.xls"
                multiple
                onChange={(e) => {
                  const files = Array.from(e.target.files || [])
                  if (files.length) mergeMutation.mutate(files)
                  e.target.value = ''
                }}
              />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={uploadMutation.isPending}
                className="btn-primary text-xs"
              >
                <Upload size={14} />
                {uploadMutation.isPending ? 'Importando...' : 'Importar Excel/CSV'}
              </button>
              <button
                type="button"
                onClick={() => mergeRef.current?.click()}
                disabled={mergeMutation.isPending}
                className="btn-secondary text-xs"
                title="Selecciona 2 o más archivos de distintas bases de datos — se unificarán eliminando duplicados"
              >
                <Merge size={14} />
                {mergeMutation.isPending ? 'Fusionando...' : 'Fusionar BD'}
              </button>
              <a
                href={`${API_BASE}/static/plantilla_estudios.xlsx`}
                download="PLANTILLA_ESTUDIOS.xlsx"
                className="btn-secondary text-xs"
                title="Descargar plantilla Excel con el formato correcto"
              >
                <Download size={14} /> Plantilla Excel
              </a>
              <button
                type="button"
                onClick={() => setShowDb(true)}
                className="btn-secondary text-xs"
                title="Ver todos los datos de los estudios"
              >
                <Database size={14} /> Ver base de datos
              </button>
              <button
                type="button"
                onClick={() => setAddingNew(true)}
                className="btn-secondary text-xs"
              >
                <Plus size={14} /> Agregar manualmente
              </button>
              <button
                type="button"
                onClick={() => {
                  if (confirm(`¿Cribar ${studies.length} estudios con IA según los criterios PICO? Esto puede tardar 1-2 minutos.`))
                    screenMutation.mutate()
                }}
                disabled={screenMutation.isPending}
                className="btn-primary text-xs"
                title="La IA analiza título, resumen y diseño de cada estudio y decide inclusión/exclusión según el PICO"
              >
                <Wand2 size={14} className={screenMutation.isPending ? 'animate-spin' : ''} />
                {screenMutation.isPending ? 'Cribando con IA...' : 'Cribar con IA'}
              </button>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {['✓', 'Estudio (Study)', 'Año', 'N', 'Eventos I / C', 'Tamaño efecto', 'RoB', ''].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold text-gray-600">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {studies.map((s) => {
                    const isIncluded = s.included !== false
                    return (
                    <tr key={s.id} className={`hover:bg-gray-50 ${!isIncluded ? 'opacity-50 bg-red-50' : ''}`}>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          title={isIncluded ? 'Incluido — clic para excluir' : `Excluido: ${s.exclusion_reason || ''} — clic para incluir`}
                          onClick={() => toggleMutation.mutate({ id: s.id, included: !isIncluded })}
                          className="transition-colors"
                        >
                          {isIncluded
                            ? <CheckCircle2 size={16} className="text-green-500" />
                            : <XCircle size={16} className="text-red-400" />}
                        </button>
                      </td>
                      <td className="px-3 py-2 max-w-[160px]">
                        <p className="font-medium truncate">{s.study_label || s.authors || '—'}</p>
                        {s.exclusion_reason && !isIncluded && (
                          <p className="text-red-400 truncate text-[10px]">{s.exclusion_reason}</p>
                        )}
                        {s.journal && isIncluded && <p className="text-gray-400 truncate">{s.journal}</p>}
                      </td>
                      <td className="px-3 py-2 text-gray-500">{s.year || '—'}</td>
                      <td className="px-3 py-2 text-gray-500">
                        {s.total_intervention != null && s.total_control != null
                          ? s.total_intervention + s.total_control
                          : s.sample_size || '—'}
                      </td>
                      <td className="px-3 py-2 text-gray-500">
                        {s.events_intervention != null
                          ? `${s.events_intervention}/${s.total_intervention} vs ${s.events_control}/${s.total_control}`
                          : s.mean_intervention != null
                          ? `${s.mean_intervention?.toFixed(1)}±${s.sd_intervention?.toFixed(1)} vs ${s.mean_control?.toFixed(1)}±${s.sd_control?.toFixed(1)}`
                          : '—'}
                      </td>
                      <td className="px-3 py-2 text-gray-500">
                        {s.effect_size != null
                          ? `${s.effect_size.toFixed(2)} [${s.effect_size_lower?.toFixed(2)}, ${s.effect_size_upper?.toFixed(2)}]`
                          : '—'}
                      </td>
                      <td className="px-3 py-2">
                        {s.rob_overall && (
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ROB_COLORS[s.rob_overall] || ''}`}>
                            {s.rob_overall === 'low' ? 'Bajo' : s.rob_overall === 'some_concerns' ? 'Algunas' : 'Alto'}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => {
                            if (confirm('¿Eliminar este estudio?')) deleteMutation.mutate(s.id)
                          }}
                          className="text-gray-300 hover:text-red-500 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  )})}
                  {studies.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-8 text-center text-gray-400">
                        <p className="mb-2">Sin estudios — importa un Excel/CSV o agrega manualmente</p>
                        <a
                          href={`${API_BASE}/static/plantilla_estudios.xlsx`}
                          download="PLANTILLA_ESTUDIOS.xlsx"
                          className="text-cochrane-500 hover:underline text-xs"
                        >
                          Descargar plantilla Excel →
                        </a>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Add manually form */}
            {addingNew && (
              <div className="p-5 border-t border-gray-100 bg-gray-50">
                <p className="text-xs font-semibold text-gray-600 mb-3 uppercase tracking-wide">
                  Agregar estudio manualmente (Add study manually)
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { field: 'study_label', label: 'Etiqueta (Label)', placeholder: 'Smith 2020' },
                    { field: 'authors', label: 'Autores (Authors)', placeholder: 'Smith J et al.' },
                    { field: 'year', label: 'Año (Year)', placeholder: '2020', type: 'number' },
                    { field: 'study_design', label: 'Diseño (Design)', placeholder: 'RCT' },
                    { field: 'events_intervention', label: 'Eventos I (Events I)', placeholder: '45', type: 'number' },
                    { field: 'total_intervention', label: 'Total I (Total I)', placeholder: '100', type: 'number' },
                    { field: 'events_control', label: 'Eventos C (Events C)', placeholder: '60', type: 'number' },
                    { field: 'total_control', label: 'Total C (Total C)', placeholder: '100', type: 'number' },
                  ].map(({ field, label, placeholder, type }) => (
                    <div key={field}>
                      <label className="label">{label}</label>
                      <input
                        className="input text-xs"
                        type={type || 'text'}
                        placeholder={placeholder}
                        onChange={setField(field as keyof Study)}
                      />
                    </div>
                  ))}
                </div>
                <div className="flex gap-2 mt-3">
                  <button
                    type="button"
                    onClick={() => createMutation.mutate(newStudy)}
                    disabled={createMutation.isPending}
                    className="btn-primary text-xs"
                  >
                    {createMutation.isPending ? 'Agregando...' : 'Agregar estudio'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setAddingNew(false)}
                    className="btn-secondary text-xs"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
