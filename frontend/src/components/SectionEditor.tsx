import { useState } from 'react'
import { Wand2, Save, ChevronDown, ChevronUp } from 'lucide-react'

interface Props {
  title: string
  sectionKey: string
  value: string
  onSave: (text: string) => void
  onGenerate: (section: string) => Promise<void>
  generating: boolean
  defaultOpen?: boolean
}

export default function SectionEditor({
  title, sectionKey, value, onSave, onGenerate, generating, defaultOpen = false,
}: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const [text, setText] = useState(value || '')
  const [dirty, setDirty] = useState(false)

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    setDirty(true)
  }

  const handleSave = () => {
    onSave(text)
    setDirty(false)
  }

  const handleGenerate = async () => {
    await onGenerate(sectionKey)
  }

  // Sync when parent updates value
  if (value !== undefined && value !== null && !dirty && text !== value) {
    setText(value)
  }

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="font-semibold text-gray-800">{title}</span>
          {text && (
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
              {wordCount} words
            </span>
          )}
        </div>
        {open ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
      </button>

      {open && (
        <div className="px-5 pb-5 border-t border-gray-100">
          <textarea
            className="section-textarea mt-4"
            value={text}
            onChange={handleChange}
            placeholder={`Escribe el texto aquí o haz clic en "Generar con IA"...`}
          />
          <div className="flex items-center justify-between mt-3">
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating}
              className="btn-primary"
            >
              <Wand2 size={15} />
              {generating ? 'Generando...' : 'Generar con IA (Generate with AI)'}
            </button>
            {dirty && (
              <button type="button" onClick={handleSave} className="btn-secondary">
                <Save size={15} /> Guardar (Save)
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
