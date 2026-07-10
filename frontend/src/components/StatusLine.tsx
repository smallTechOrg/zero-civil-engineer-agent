import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface StatusLineProps {
  text: string
  warnings: string[]
}

export default function StatusLine({ text, warnings }: StatusLineProps) {
  return (
    <div className="space-y-3">
      <div
        data-testid="status-line"
        aria-live="polite"
        className="min-h-[1.75rem] text-lg leading-relaxed text-slate-800 [&_p]:m-0 [&_strong]:font-semibold"
      >
        {text ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        ) : (
          <span className="text-slate-400">Waiting for a design request…</span>
        )}
      </div>
      {warnings.map((message, i) => (
        <div
          key={i}
          data-testid="warning-banner"
          role="status"
          className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-base text-amber-900"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="mt-0.5 shrink-0"
            aria-hidden="true"
          >
            <path d="M12 3 22 20H2L12 3Z" strokeLinejoin="round" />
            <path d="M12 10v4M12 17.5v.5" strokeLinecap="round" />
          </svg>
          <span>
            <span className="font-semibold">Flagged: </span>
            {message}
          </span>
        </div>
      ))}
    </div>
  )
}
