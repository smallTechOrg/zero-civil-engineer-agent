'use client'

export type StubStage = 'simulate' | 'test' | 'approve'

interface StubCopy {
  numeral: string
  title: string
  icon: string
  sentence: string
}

// One descriptive sentence per coming lifecycle stage. Clearly non-functional —
// dashed border, muted icon, "Coming in a later release" badge (spec/ui.md
// "Stub Presentation Rules": a stub must NEVER look like a bug — no spinner,
// no red, no disabled-as-error).
const STUBS: Record<StubStage, StubCopy> = {
  simulate: {
    numeral: '④',
    title: 'Simulate',
    icon: '∿',
    sentence: 'Simulate will run parametric load sweeps against this design to map its behaviour across the operating envelope.',
  },
  test: {
    numeral: '⑤',
    title: 'Test',
    icon: '⚗',
    sentence: 'Test will generate a physical-inspection and load-test protocol traceable to each governing clause of this design.',
  },
  approve: {
    numeral: '⑥',
    title: 'Approve',
    icon: '✍',
    sentence: 'Approve will route this design through a digital sign-off workflow with an auditable approval trail.',
  },
}

interface StageStubProps {
  stage: StubStage
}

export default function StageStub({ stage }: StageStubProps) {
  const copy = STUBS[stage]
  return (
    <div
      data-testid={`stage-stub-${stage}`}
      className="flex min-h-[24rem] flex-1 flex-col items-center justify-center gap-5 rounded-2xl border-2 border-dashed border-neutral-700 bg-neutral-900/40 p-10 text-center"
    >
      <span
        aria-hidden="true"
        className="flex h-16 w-16 items-center justify-center rounded-full border border-dashed border-neutral-700 text-3xl text-neutral-600"
      >
        {copy.icon}
      </span>
      <div className="flex items-center gap-2">
        <span className="text-lg text-neutral-500">{copy.numeral}</span>
        <h2 className="text-2xl font-bold text-neutral-200">{copy.title}</h2>
      </div>
      <span
        data-testid={`stage-stub-badge-${stage}`}
        className="rounded-full border border-dashed border-neutral-600 bg-neutral-800/60 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-neutral-400"
      >
        ⊘ Coming in a later release
      </span>
      <p className="max-w-md text-base leading-relaxed text-neutral-400">{copy.sentence}</p>
    </div>
  )
}
