'use client'

import CalcSheet from './CalcSheet'
import DrawingViewer from './DrawingViewer'
import LibraryPanel from './LibraryPanel'
import Model3DViewer from './Model3DViewer'
import ProofCheckPanel from './ProofCheckPanel'
import TypeSummaryPanel from './TypeSummaryPanel'
import type { CalcSheetData, ComplianceData, TypeSummary, Verdict } from '@/lib/types'

export type TabId = 'summary' | 'drawing' | 'calc-sheet' | 'proof-check' | '3d-model' | 'library'

interface TabDef {
  id: TabId
  label: string
}

const TABS: TabDef[] = [
  { id: 'summary', label: 'Stability' },
  { id: 'drawing', label: 'Drawing' },
  { id: 'calc-sheet', label: 'Calc Sheet' },
  { id: 'proof-check', label: 'Proof-Check' },
  { id: '3d-model', label: '3D Model' },
  { id: 'library', label: 'Library' },
]

interface ArtefactTabsProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
  componentType: string | null
  typeSummary: TypeSummary | null
  svgMarkup: string | null
  dxfUrl: string | null
  calcSheet: CalcSheetData | null
  calcComposing: boolean
  compliance: ComplianceData | null
  memoMarkdown: string | null
  bmdSvg: string | null
  sfdSvg: string | null
  verdict: Verdict | null
  reviewActive: boolean
  isRunning: boolean
  drawActive: boolean
  runFailed: boolean
  hasRun: boolean
  glbUrl: string | null
  stepUrl: string | null
  onSelectRun: (runId: string) => void
  activeRunId: string | null
  libraryRefreshKey: number
}

export default function ArtefactTabs({
  activeTab,
  onTabChange,
  componentType,
  typeSummary,
  svgMarkup,
  dxfUrl,
  calcSheet,
  calcComposing,
  compliance,
  memoMarkdown,
  bmdSvg,
  sfdSvg,
  verdict,
  reviewActive,
  isRunning,
  drawActive,
  runFailed,
  hasRun,
  glbUrl,
  stepUrl,
  onSelectRun,
  activeRunId,
  libraryRefreshKey,
}: ArtefactTabsProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div role="tablist" aria-label="Artefacts" className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map(tab => {
          const active = tab.id === activeTab
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              data-testid={`tab-${tab.id}`}
              aria-selected={active}
              aria-controls={`panel-${tab.id}`}
              onClick={() => onTabChange(tab.id)}
              className={`-mb-px inline-flex items-center gap-2 rounded-t-lg border-x border-t px-4 py-2.5 text-base font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${
                active
                  ? 'border-slate-200 border-b-white bg-white text-indigo-700'
                  : 'border-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              {tab.label}
            </button>
          )
        })}
      </div>
      <div
        role="tabpanel"
        id={`panel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
        className="min-h-0 flex-1 overflow-auto bg-white p-4"
      >
        {activeTab === 'summary' && (
          <TypeSummaryPanel
            componentType={componentType}
            typeSummary={typeSummary}
            isRunning={isRunning}
            runFailed={runFailed}
            hasRun={hasRun}
          />
        )}
        {activeTab === 'drawing' && (
          <DrawingViewer
            svgMarkup={svgMarkup}
            dxfUrl={dxfUrl}
            isRunning={isRunning}
            drawActive={drawActive}
            runFailed={runFailed}
            hasRun={hasRun}
          />
        )}
        {activeTab === 'calc-sheet' && (
          <CalcSheet
            sheet={calcSheet}
            isRunning={isRunning}
            composing={calcComposing}
            runFailed={runFailed}
            hasRun={hasRun}
          />
        )}
        {activeTab === 'proof-check' && (
          <ProofCheckPanel
            compliance={compliance}
            memoMarkdown={memoMarkdown}
            bmdSvg={bmdSvg}
            sfdSvg={sfdSvg}
            verdict={verdict}
            isRunning={isRunning}
            reviewActive={reviewActive}
            runFailed={runFailed}
            hasRun={hasRun}
          />
        )}
        {activeTab === '3d-model' && (
          <Model3DViewer glbUrl={glbUrl} stepUrl={stepUrl} isRunning={isRunning} runFailed={runFailed} hasRun={hasRun} />
        )}
        {activeTab === 'library' && (
          <LibraryPanel
            onSelectRun={onSelectRun}
            selectionDisabled={isRunning}
            activeRunId={activeRunId}
            refreshKey={libraryRefreshKey}
          />
        )}
      </div>
    </div>
  )
}
