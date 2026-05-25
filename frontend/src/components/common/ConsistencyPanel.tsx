import { AlertTriangle, ShieldCheck } from "lucide-react"
import type { ConsistencyEntity, ConsistencyReport } from "@/types/education"

interface ConsistencyPanelProps {
  report: ConsistencyReport
  title?: string
}

export function ConsistencyPanel({ report, title = "实体与可靠性检查" }: ConsistencyPanelProps) {
  const displayExpectedEntities = filterCoreEntities(report.expected_entities || [])
  const displayMentionedEntities = filterCoreEntities(report.mentioned_entities || [])
  const displayMissingEntities = filterCoreEntities(report.missing_entities || [])
  const displayUnsupportedEntities = filterUnsupportedEntities(report.unsupported_entities || [])
  const displayEntityRecall = displayExpectedEntities.length
    ? displayMentionedEntities.length / displayExpectedEntities.length
    : report.entity_recall
  const displayHallucinationRate = displayUnsupportedEntities.length
    ? displayUnsupportedEntities.length / Math.max(1, displayUnsupportedEntities.length + displayMentionedEntities.length)
    : 0

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
          <Metric label="核心实体召回率" value={formatPercent(displayEntityRecall)} />
          <Metric label="未匹配专名率" value={formatPercent(displayHallucinationRate)} />
          <Metric label="图谱支撑率" value={formatPercent(report.knowledge_support_ratio)} />
          <Metric label="未支撑概念率" value={formatPercent(report.unsupported_concept_rate)} />
        </div>

        <EntityList title="已命中核心图谱实体" items={displayMentionedEntities} emptyText="暂无命中的核心图谱实体" />
        <EntityList title="未覆盖核心图谱实体" items={displayMissingEntities} emptyText="没有未覆盖核心实体" />
        <EntityList title="未匹配到图谱的专名" items={displayUnsupportedEntities} emptyText="没有发现未匹配专名" />

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

function filterCoreEntities(items: ConsistencyEntity[]) {
  return dedupeEntities(items.filter((item) => isCoreEntity(item))).slice(0, 12)
}

function filterUnsupportedEntities(items: ConsistencyEntity[]) {
  return dedupeEntities(items.filter((item) => isDisplayableUnsupportedEntity(item))).slice(0, 12)
}

function dedupeEntities(items: ConsistencyEntity[]) {
  const seen = new Set<string>()
  const result: ConsistencyEntity[] = []
  items.forEach((item) => {
    const key = normalizeEntityName(item.name)
    if (!key || seen.has(key)) return
    seen.add(key)
    result.push(item)
  })
  return result
}

function isCoreEntity(item: ConsistencyEntity) {
  const name = item.name?.trim()
  if (!name || name.length > 120) return false
  const type = item.type?.toLowerCase()
  return !type || ["chapter", "section", "concept", "formula", "theorem", "example"].includes(type)
}

function isDisplayableUnsupportedEntity(item: ConsistencyEntity) {
  const name = item.name?.trim()
  if (!name || name.length < 2 || name.length > 80) return false
  if (isLikelyChinesePhrase(name)) return false
  return /[A-Z0-9]/.test(name) || /\b(?:Equation|Eq\.?|Formula|Table|Figure)\s+\d/i.test(name)
}

function isLikelyChinesePhrase(value: string) {
  if (!/[\u4e00-\u9fff]/.test(value)) return false
  if (/[A-Za-z0-9]/.test(value)) return false
  return true
}

function normalizeEntityName(value?: string) {
  return (value || "").toLowerCase().replace(/\s+/g, " ").trim()
}

function formatPercent(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "0%"
  return `${Math.round(value * 100)}%`
}
