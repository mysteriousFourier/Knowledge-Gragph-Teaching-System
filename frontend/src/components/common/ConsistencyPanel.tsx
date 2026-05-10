import { AlertTriangle, ShieldCheck } from "lucide-react"
import type { ConsistencyEntity, ConsistencyReport } from "@/types/education"

interface ConsistencyPanelProps {
  report: ConsistencyReport
  title?: string
}

export function ConsistencyPanel({ report, title = "实体与可靠性检查" }: ConsistencyPanelProps) {
  return (
    <section className="rounded-lg border bg-card">
      <div className="flex items-center justify-between gap-3 border-b p-4">
        <h2 className="flex items-center gap-2 font-semibold">
          <ShieldCheck size={18} />
          {title}
        </h2>
        {report.is_safe_to_show === false && <AlertTriangle size={18} className="text-amber-500" />}
      </div>
      <div className="space-y-4 p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Metric label="实体召回率" value={formatPercent(report.entity_recall)} />
          <Metric label="实体幻觉率" value={formatPercent(report.entity_hallucination_rate)} />
          <Metric label="图谱支撑率" value={formatPercent(report.knowledge_support_ratio)} />
          <Metric label="未支撑概念率" value={formatPercent(report.unsupported_concept_rate)} />
        </div>

        <EntityList title="已命中图谱实体" items={report.mentioned_entities || []} emptyText="暂无命中的图谱实体" />
        <EntityList title="缺失实体" items={report.missing_entities || []} emptyText="没有缺失实体" />
        <EntityList title="疑似幻觉实体" items={report.unsupported_entities || []} emptyText="没有发现疑似幻觉实体" />

        {!!report.warnings?.length && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            {report.warnings.map((warning) => (
              <div key={warning}>{warning}</div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  )
}

function EntityList({ title, items, emptyText }: { title: string; items: ConsistencyEntity[]; emptyText: string }) {
  return (
    <div>
      <div className="mb-2 text-sm font-medium">{title}</div>
      {items.length ? (
        <div className="flex max-h-28 flex-wrap gap-2 overflow-auto">
          {items.slice(0, 24).map((item) => (
            <span key={`${item.id || item.name}-${item.source_index || item.count || ""}`} className="rounded-full border bg-background px-2.5 py-1 text-xs">
              {item.name}
            </span>
          ))}
        </div>
      ) : (
        <div className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">{emptyText}</div>
      )}
    </div>
  )
}

function formatPercent(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "0%"
  return `${Math.round(value * 100)}%`
}
