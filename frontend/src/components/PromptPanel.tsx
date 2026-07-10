'use client'

import { useEffect, useRef } from 'react'

export const CANONICAL_PROMPT =
  'single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading'

export type PromptMode = 'design' | 'answer' | 'refine'

const BUTTON_LABEL: Record<PromptMode, string> = {
  design: 'Design',
  answer: 'Answer',
  refine: 'Refine',
}

interface PromptPanelProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  mode: PromptMode
  disabled: boolean
  disabledReason: string | null
  formError: string | null
  clarificationQuestion: string | null
}

export default function PromptPanel({
  value,
  onChange,
  onSubmit,
  mode,
  disabled,
  disabledReason,
  formError,
  clarificationQuestion,
}: PromptPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (clarificationQuestion && !disabled) textareaRef.current?.focus()
  }, [clarificationQuestion, disabled])

  return (
    <form
      className="space-y-3"
      onSubmit={e => {
        e.preventDefault()
        onSubmit()
      }}
    >
      {clarificationQuestion && (
        <div
          data-testid="clarification-card"
          role="status"
          className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3"
        >
          <p className="text-base font-semibold text-amber-900">One question:</p>
          <p className="mt-1 text-base leading-relaxed text-amber-900">{clarificationQuestion}</p>
        </div>
      )}

      <label htmlFor="prompt-input" className="block text-sm font-semibold uppercase tracking-wide text-slate-500">
        {mode === 'answer' ? 'Your answer' : 'Design request'}
      </label>
      <textarea
        id="prompt-input"
        data-testid="prompt-input"
        ref={textareaRef}
        rows={4}
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault()
            onSubmit()
          }
        }}
        disabled={disabled}
        placeholder={CANONICAL_PROMPT}
        className="w-full resize-y rounded-lg border border-slate-300 bg-white p-3 text-base leading-relaxed text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:bg-slate-100 disabled:text-slate-500"
      />

      {formError && (
        <p role="alert" className="text-base font-medium text-red-700">
          {formError}
        </p>
      )}

      <div className="space-y-2">
        <button
          type="submit"
          data-testid="prompt-submit"
          disabled={disabled}
          className="w-full rounded-lg bg-indigo-600 px-5 py-3 text-lg font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {BUTTON_LABEL[mode]}
        </button>
        {disabled && disabledReason && <p className="text-sm text-slate-600">{disabledReason}</p>}
        {!disabled && <p className="text-sm text-slate-400">Ctrl/Cmd + Enter to submit</p>}
      </div>
    </form>
  )
}
