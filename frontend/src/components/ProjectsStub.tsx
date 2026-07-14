'use client'

import { useState } from 'react'

/**
 * Projects grouping — a clearly-labelled `⊘ coming` STUB (spec/ui.md "Stub
 * Presentation Rules"): muted, dashed, a "coming" badge, disclosure reveals the
 * intent. It must NEVER read as a real (empty) list, an error, or a bug.
 */
export default function ProjectsStub() {
  const [open, setOpen] = useState(false)
  return (
    <div data-testid="projects-stub" className="rounded-lg border border-dashed border-studio-border">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-base text-studio-text-dim transition-colors hover:text-studio-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-studio-accent"
      >
        <span aria-hidden className="text-studio-text-faint">
          {open ? '▾' : '▸'}
        </span>
        <span aria-hidden className="text-studio-text-faint">
          ⊘
        </span>
        <span className="font-medium">Projects</span>
        <span className="ml-auto rounded-full border border-studio-border-strong bg-studio-panel-2 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-studio-text-faint">
          coming
        </span>
      </button>
      {open && (
        <p className="px-3 pb-3 text-sm leading-relaxed text-studio-text-faint">
          Group related designs into a project — coming in a later release.
        </p>
      )}
    </div>
  )
}
