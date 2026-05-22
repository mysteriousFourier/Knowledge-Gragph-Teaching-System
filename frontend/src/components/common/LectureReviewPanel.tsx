import { AlertTriangle, Database, ShieldCheck } from "lucide-react"
import { ConsistencyPanel } from "@/components/common/ConsistencyPanel"
import { EvidenceSummary } from "@/components/common/EvidenceSummary"
import type { ConsistencyReport } from "@/types/education"

interface LectureReviewPanelProps {
  learningPlan?: unknown
  sources?: unknown[]
  retrievalContext?: string
  warning?: string
  consistencyReport?: ConsistencyReport
  className?: string
}

export function LectureReviewPanel({ learningPlan, sources, retrievalContext, warning, consistencyReport, className }: LectureReviewPanelProps) {
  const derivedWarnings = buildWarnings(consistencyReport)
  const hasReview = !!learningPlan || !!sources?.length || !!retrievalContext || !!warning || !!consistencyReport
  if (!hasReview) return null

  return (
    <section className={className}>
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <ShieldCheck size={16} />
        Lecture review aids
      </div>
      <div className="space-y-3">
        {learningPlan || sources?.length || retrievalContext || warning ? (
          <EvidenceSummary
            learningPlan={learningPlan}
            sources={sources}
            retrievalContext={retrievalContext}
            warning={warning}
          />
        ) : null}
        {consistencyReport ? <ConsistencyPanel report={consistencyReport} title="Grounding and risk metrics" /> : null}
        {derivedWarnings.length ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <div className="mb-2 flex items-center gap-2 font-medium">
              <AlertTriangle size={16} />
              Low-confidence notes
            </div>
            {derivedWarnings.map((warning) => (
              <div key={warning}>{warning}</div>
            ))}
          </div>
        ) : null}
        <div className="rounded-lg border bg-card p-4 text-sm text-muted-foreground">
          <div className="flex items-center gap-2 font-medium text-foreground">
            <Database size={16} />
            Review scope
          </div>
          <p className="mt-2">
            These evidence and risk indicators are for teacher editing only. They are stored separately from the lecture script and are not inserted into the generated prose.
          </p>
        </div>
      </div>
    </section>
  )
}

function buildWarnings(report?: ConsistencyReport) {
  const warnings = [...(report?.warnings || [])]
  const hallucinationRate = report?.entity_hallucination_rate
  const supportRatio = report?.knowledge_support_ratio
  const unsupportedRate = report?.unsupported_concept_rate
  if (typeof hallucinationRate === "number" && hallucinationRate >= 0.25) {
    warnings.push(`Entity hallucination rate is ${formatPercent(hallucinationRate)}; review unsupported terms before use.`)
  }
  if (typeof supportRatio === "number" && supportRatio > 0 && supportRatio < 0.5) {
    warnings.push(`Knowledge support ratio is ${formatPercent(supportRatio)}; add evidence or simplify the script.`)
  }
  if (typeof unsupportedRate === "number" && unsupportedRate >= 0.25) {
    warnings.push(`Unsupported concept rate is ${formatPercent(unsupportedRate)}; verify low-confidence explanations.`)
  }
  return Array.from(new Set(warnings))
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}
