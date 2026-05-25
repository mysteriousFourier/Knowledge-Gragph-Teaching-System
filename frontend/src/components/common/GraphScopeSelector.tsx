import { useMemo } from "react"
import { BookOpen, ChevronDown, ChevronRight, Network, Search } from "lucide-react"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import type { GraphContextTreeNode, GraphNodeContextResponse } from "@/types/education"
import type { GraphNode, GraphRelation } from "@/types/graph"

export type GraphScopeTreeNode = {
  id: string
  label: string
  type: string
  children: GraphScopeTreeNode[]
  match: boolean
}

const RESOURCE_TYPES = new Set(["formula", "note", "table", "figure", "example"])
const STRUCTURAL_TYPES = new Set(["part", "chapter", "section"])

export function GraphTreePanel({
  tree,
  search,
  selectedNodeIds,
  expandedNodeIds,
  isLoading,
  nodeCount,
  relationCount,
  onSearch,
  onSelect,
  onToggle,
}: {
  tree: GraphScopeTreeNode[]
  search: string
  selectedNodeIds: string[]
  expandedNodeIds: Set<string>
  isLoading: boolean
  nodeCount: number
  relationCount: number
  onSearch: (value: string) => void
  onSelect: (value: string) => void
  onToggle: (value: string) => void
}) {
  const selectedIdSet = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds])

  return (
    <section className="rounded-lg border bg-card">
      <div className="border-b p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 font-semibold">
            <Network size={18} />
            图谱章节树
          </h2>
          <span className="text-xs text-muted-foreground">{nodeCount} 节点 / {relationCount} 关系</span>
        </div>
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
          <input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="搜索章节、大节、小节或知识点"
            className="w-full rounded-lg border bg-background py-2 pl-9 pr-3 text-sm"
          />
        </label>
      </div>
      <div className="max-h-[520px] overflow-auto p-2">
        {isLoading ? (
          <div className="py-10">
            <LoadingSpinner text="正在读取图谱..." />
          </div>
        ) : tree.length ? (
          tree.map((node) => (
            <TreeRow
              key={node.id}
              node={node}
              depth={0}
              selectedNodeIds={selectedIdSet}
              expandedNodeIds={expandedNodeIds}
              onSelect={onSelect}
              onToggle={onToggle}
            />
          ))
        ) : (
          <div className="p-4 text-sm text-muted-foreground">没有可用章节树，请先导入或生成图谱。</div>
        )}
      </div>
    </section>
  )
}

export function GraphContextPanel({
  isLoading,
  context,
  emptyText = "选择左侧节点后，系统会按 contains 关系取整棵子树进行备课。",
}: {
  isLoading: boolean
  context?: GraphNodeContextResponse
  emptyText?: string
}) {
  return (
    <section className="rounded-lg border bg-card">
      <div className="border-b p-4">
        <h2 className="flex items-center gap-2 font-semibold">
          <BookOpen size={18} />
          备课范围
        </h2>
      </div>
      <div className="p-4">
        {isLoading ? (
          <LoadingSpinner text="正在构建节点子树..." />
        ) : context?.success ? (
          <div className="space-y-3">
            <div>
              <div className="text-sm font-medium">{context.chapter_title || "未命名节点"}</div>
              <div className="text-xs text-muted-foreground">
                {context.scope?.root_count && context.scope.root_count > 1 ? `${context.scope.root_count} 个同级范围，` : ""}
                整棵子树 {context.scope?.selected_count ?? 0} 个节点，引用资源 {context.scope?.referenced_count ?? 0} 个
                {context.scope?.truncated ? "，已截断" : ""}
              </div>
            </div>
            {context.tree && <ContextTree tree={context.tree} />}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">{emptyText}</div>
        )}
      </div>
    </section>
  )
}

function TreeRow({
  node,
  depth,
  selectedNodeIds,
  expandedNodeIds,
  onSelect,
  onToggle,
}: {
  node: GraphScopeTreeNode
  depth: number
  selectedNodeIds: Set<string>
  expandedNodeIds: Set<string>
  onSelect: (value: string) => void
  onToggle: (value: string) => void
}) {
  const hasChildren = node.children.length > 0
  const isExpanded = expandedNodeIds.has(node.id)
  const isSelected = selectedNodeIds.has(node.id)
  const visibleChildren = isExpanded ? node.children : []
  const indent = { paddingLeft: `${Math.min(depth * 18, 72)}px` }

  return (
    <div>
      <div className={`flex items-center gap-1 rounded-md ${isSelected ? "bg-primary text-primary-foreground" : node.match ? "bg-muted" : "hover:bg-muted"}`} style={indent}>
        <button
          type="button"
          onClick={() => onToggle(node.id)}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded border-0 bg-transparent p-0"
          aria-label={isExpanded ? "收起节点" : "展开节点"}
        >
          {hasChildren ? (isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />) : <span className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={() => onSelect(node.id)}
          title={node.label}
          className="min-w-0 flex-1 border-0 bg-transparent px-1 py-2 text-left"
        >
          <span className="block break-words text-sm font-medium leading-snug">{node.label}</span>
          <span className={`text-[11px] ${isSelected ? "text-primary-foreground/75" : "text-muted-foreground"}`}>{typeLabel(node.type)} · {node.children.length} 子节点</span>
        </button>
      </div>
      {visibleChildren.map((child) => (
        <TreeRow
          key={child.id}
          node={child}
          depth={depth + 1}
          selectedNodeIds={selectedNodeIds}
          expandedNodeIds={expandedNodeIds}
          onSelect={onSelect}
          onToggle={onToggle}
        />
      ))}
    </div>
  )
}

function ContextTree({ tree }: { tree: GraphContextTreeNode }) {
  return (
    <div className="max-h-[240px] overflow-auto rounded border bg-background p-2 text-sm">
      {renderContextTree(tree)}
    </div>
  )
}

function renderContextTree(tree: GraphContextTreeNode, depth = 0): React.ReactNode {
  return (
    <div key={tree.id} style={{ paddingLeft: `${Math.min(depth * 14, 56)}px` }}>
      <div className="flex min-w-0 items-center gap-2 py-1">
        <span className="shrink-0 rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground">{typeLabel(tree.type)}</span>
        <span className="break-words" title={tree.label}>{tree.label}</span>
      </div>
      {(tree.children || []).map((child) => renderContextTree(child, depth + 1))}
    </div>
  )
}

export function buildGraphScopeTree(nodes: GraphNode[], relationships: GraphRelation[], search: string): GraphScopeTreeNode[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const childrenByParent = new Map<string, string[]>()
  const childIds = new Set<string>()
  relationships.forEach((relation) => {
    if ((relation.relation_type || relation.type) !== "contains") return
    if (!nodeById.has(relation.source_id) || !nodeById.has(relation.target_id)) return
    childrenByParent.set(relation.source_id, [...(childrenByParent.get(relation.source_id) || []), relation.target_id])
    childIds.add(relation.target_id)
  })

  const term = search.trim().toLowerCase()
  const rootIds = nodes
    .filter((node) => !childIds.has(node.id) && (node.type === "chapter" || childrenByParent.has(node.id)))
    .map((node) => node.id)
    .sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))

  const build = (id: string): GraphScopeTreeNode | null => {
    const node = nodeById.get(id)
    if (!node) return null
    const children = (childrenByParent.get(id) || [])
      .filter((childId) => nodeById.has(childId) && !RESOURCE_TYPES.has(nodeById.get(childId)?.type || ""))
      .sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
      .map(build)
      .filter(Boolean) as GraphScopeTreeNode[]
    const haystack = `${node.label} ${node.type} ${node.content || ""}`.toLowerCase()
    const selfMatch = !term || haystack.includes(term)
    const descendantMatch = children.some((child) => child.match)
    if (term && !selfMatch && !descendantMatch) return null
    return {
      id,
      label: node.label || id,
      type: node.type || "concept",
      children,
      match: selfMatch || descendantMatch,
    }
  }

  const roots = rootIds.map(build).filter(Boolean) as GraphScopeTreeNode[]
  if (roots.length) return roots
  return nodes
    .filter((node) => STRUCTURAL_TYPES.has(node.type || ""))
    .sort((a, b) => compareGraphScopeNodes(a, b))
    .slice(0, 80)
    .map((node) => ({ id: node.id, label: node.label || node.id, type: node.type || "concept", children: [], match: true }))
}

export function buildParentByChild(relationships: GraphRelation[]) {
  const parentByChild = new Map<string, string>()
  relationships.forEach((relation) => {
    if ((relation.relation_type || relation.type) === "contains") {
      parentByChild.set(relation.target_id, relation.source_id)
    }
  })
  return parentByChild
}

export function resolveNextGraphScopeSelection(previous: string[], nodeId: string, parentByChild: Map<string, string>) {
  if (!previous.length) return [nodeId]
  if (previous.includes(nodeId)) {
    return previous.length === 1 ? [] : previous.filter((item) => item !== nodeId)
  }
  const selectedParent = parentByChild.get(previous[0]) || ""
  const nextParent = parentByChild.get(nodeId) || ""
  if (selectedParent && selectedParent === nextParent) {
    return [...previous, nodeId]
  }
  return [nodeId]
}

export function sortGraphScopeNodeIds(nodeIds: string[], nodeById: Map<string, GraphNode>) {
  return [...nodeIds].sort((left, right) => compareGraphScopeNodes(nodeById.get(left), nodeById.get(right)))
}

export function collectMatchedGraphScopeBranches(nodes: GraphScopeTreeNode[], target: Set<string>) {
  nodes.forEach((node) => {
    if (node.match) target.add(node.id)
    collectMatchedGraphScopeBranches(node.children, target)
  })
}

function compareGraphScopeNodes(left?: GraphNode, right?: GraphNode) {
  const leftKey = graphScopeNodeOrderKey(left)
  const rightKey = graphScopeNodeOrderKey(right)
  return leftKey.localeCompare(rightKey, undefined, { numeric: true, sensitivity: "base" })
}

function graphScopeNodeOrderKey(node?: GraphNode) {
  if (node?.id === "toc::root") return "0000|toc-root"
  const metadata = node?.metadata || {}
  const tocPage = Number(metadata.toc_page || 0)
  if (tocPage > 0 || metadata.toc_node_id) {
    const tocLevel = Number(metadata.toc_level || 0)
    const tocNodeId = String(metadata.toc_node_id || node?.id || "")
    return `toc|${String(tocPage).padStart(5, "0")}|${String(tocLevel).padStart(2, "0")}|${tocNodeId}`
  }
  const chapter = String(metadata.chapter || node?.id || "")
  const sourceUnit = String(metadata.source_unit || metadata.source || "")
  const blockIndex = Number(metadata.block_index || 0)
  const typeRank = node?.type === "part" ? 0 : node?.type === "chapter" ? 1 : node?.type === "section" ? 2 : 3
  return `${chapter}|${typeRank}|${sourceUnit}|${String(blockIndex).padStart(5, "0")}|${node?.label || ""}`
}

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    part: "篇章",
    chapter: "章节",
    section: "小节",
    discussion: "正文",
    proposition: "命题",
    derivation: "推导",
    formula: "公式",
    note: "表格",
    table: "表格",
    figure: "图片",
    example: "例题",
    concept: "概念",
    selection: "多选范围",
  }
  return labels[type] || type || "节点"
}
