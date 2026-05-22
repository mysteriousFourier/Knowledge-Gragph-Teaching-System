import { Database, Network, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"

interface EvidenceSummaryProps {
  learningPlan?: unknown
  sources?: unknown[]
  retrievalContext?: string
  warning?: string
  className?: string
}

export function EvidenceSummary({ learningPlan, sources, retrievalContext, warning, className }: EvidenceSummaryProps) {
  const plan = isRecord(learningPlan) ? learningPlan : undefined
  const evidence = Array.isArray(plan?.evidence) ? plan.evidence : []
  const sourceItems = sources?.length ? sources : evidence
  const mode = evidence.some((item) => isRecord(item) && item.source === "graph")
    ? "图谱证据"
    : sourceItems.length || retrievalContext
      ? "RAG证据"
      : "模型兜底"

  const Icon = mode === "图谱证据" ? Network : mode === "RAG证据" ? Database : Sparkles

  return (
    <section className={cn("rounded-lg border bg-card p-4", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Icon size={16} />
          证据来源
        </h3>
        <span className="rounded-full border bg-background px-2.5 py-1 text-xs text-muted-foreground">{mode}</span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <Metric label="证据条目" value={String(sourceItems.length)} />
        <Metric label="允许概念" value={String(Array.isArray(plan?.allowed_concepts) ? plan.allowed_concepts.length : 0)} />
        <Metric label="检索上下文" value={retrievalContext ? "有" : "无"} />
      </div>
      {sourceItems.length > 0 && (
        <div className="mt-3 flex max-h-24 flex-wrap gap-2 overflow-auto">
          {sourceItems.slice(0, 12).map((item, index) => {
            const record = isRecord(item) ? item : {}
            const label = String(record.label || record.title || record.name || record.source || `证据 ${index + 1}`)
            return (
              <span key={`${label}-${index}`} className="rounded-full border bg-background px-2.5 py-1 text-xs">
                {label}
              </span>
            )
          })}
        </div>
      )}
      {warning && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{warning}</div>}
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-background px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-semibold">{value}</div>
    </div>
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}
