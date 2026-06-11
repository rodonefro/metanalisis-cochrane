import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp, Wand2, Save } from 'lucide-react'
import toast from 'react-hot-toast'
import { generateSection, updateReview } from '../services/api'

const CITATION_STYLES = [
  {
    value: 'vancouver',
    label: 'Vancouver (Cochrane / PubMed)',
    description: 'Numerada superíndice. Usada en Cochrane y revistas biomédicas.',
  },
  {
    value: 'nlm',
    label: 'NLM / MEDLINE',
    description: 'Formato de la Biblioteca Nacional de Medicina de EE.UU.',
  },
  {
    value: 'apa',
    label: 'APA 7ª edición',
    description: 'Usada en psicología y ciencias sociales.',
  },
  {
    value: 'harvard',
    label: 'Harvard',
    description: 'Autor-año entre paréntesis.',
  },
  {
    value: 'cochrane',
    label: 'Cochrane estándar',
    description: 'Formato oficial de revisiones Cochrane.',
  },
]

interface Props {
  reviewId: number
  currentStyle: string
  currentText: string
}

export default function ReferencesSection({ reviewId, currentStyle, currentText }: Props) {
  const [open, setOpen] = useState(false)
  const [style, setStyle] = useState(currentStyle || 'vancouver')
  const [text, setText] = useState(currentText || '')
  const [generating, setGenerating] = useState(false)
  const [dirty, setDirty] = useState(false)

  const handleGenerate = async () => {
    // Save the selected style first
    await updateReview(reviewId, { citation_style: style })
    setGenerating(true)
    try {
      const res = await generateSection(reviewId, 'references')
      setText(res.text)
      setDirty(false)
      toast.success('Referencias generadas')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Error al generar referencias')
    } finally {
      setGenerating(false)
    }
  }

  const handleSave = async () => {
    try {
      await updateReview(reviewId, { references: text, citation_style: style })
      setDirty(false)
      toast.success('Referencias guardadas')
    } catch {
      toast.error('Error al guardar')
    }
  }

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0
  const selectedStyle = CITATION_STYLES.find(s => s.value === style)

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          <BookOpen size={18} className="text-cochrane-500" />
          <span className="font-semibold text-gray-800">
            Referencias bibliográficas (References)
          </span>
          {text && (
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
              {wordCount} palabras
            </span>
          )}
          {style && (
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
              {selectedStyle?.label || style}
            </span>
          )}
        </div>
        {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
      </button>

      {open && (
        <div className="border-t border-gray-100 px-5 pb-5 space-y-4">

          {/* Selector de estilo */}
          <div className="mt-4">
            <label className="label">
              Estilo de cita (Citation style)
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
              {CITATION_STYLES.map(s => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => { setStyle(s.value); setDirty(true) }}
                  className={`text-left p-3 rounded-lg border-2 transition-colors ${
                    style === s.value
                      ? 'border-cochrane-500 bg-cochrane-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <p className={`text-sm font-semibold ${style === s.value ? 'text-cochrane-700' : 'text-gray-700'}`}>
                    {s.label}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">{s.description}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Área de texto */}
          <textarea
            className="section-textarea font-mono text-xs"
            value={text}
            onChange={e => { setText(e.target.value); setDirty(true) }}
            placeholder="Las referencias aparecerán aquí al generarlas con IA, o puedes escribirlas manualmente..."
            rows={10}
          />

          {/* Botones */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating}
              className="btn-primary"
            >
              <Wand2 size={15} />
              {generating
                ? 'Generando referencias...'
                : `Generar con IA — ${selectedStyle?.label || style}`}
            </button>
            {dirty && (
              <button type="button" onClick={handleSave} className="btn-secondary">
                <Save size={15} /> Guardar (Save)
              </button>
            )}
          </div>

          {/* Nota informativa */}
          <p className="text-xs text-gray-400 bg-gray-50 rounded-lg p-3">
            <strong>Nota:</strong> La IA genera las referencias usando los metadatos de los estudios incluidos
            (autores, año, título, revista). Para mayor precisión, asegúrate de que cada estudio
            tenga su información bibliográfica completa.
          </p>
        </div>
      )}
    </div>
  )
}
