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

const HIDDEN_TOC_ENTRY_TYPES = new Set(["index", "literature_cited"])

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
  const rawChildrenByParent = new Map<string, string[]>()
  relationships.forEach((relation) => {
    if ((relation.relation_type || relation.type) !== "contains") return
    if (!nodeById.has(relation.source_id) || !nodeById.has(relation.target_id)) return
    rawChildrenByParent.set(relation.source_id, [...(rawChildrenByParent.get(relation.source_id) || []), relation.target_id])
  })

  const term = search.trim().toLowerCase()
  const rootIds = nodeById.has("toc::root")
    ? ["toc::root"]
    : nodes
        .filter((node) => isGraphScopeDisplayNode(node))
        .map((node) => node.id)
    .sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))

  const canonicalChapterForToc = (id: string) => canonicalChapterChildren(id, rawChildrenByParent, nodeById)[0]

  const displayChildrenFor = (id: string) => {
    const node = nodeById.get(id)
    const directChildren = rawChildrenByParent.get(id) || []
    const displayChildren: string[] = []
    const seen = new Set<string>()
    const add = (childId: string) => {
      if (seen.has(childId)) return
      const child = nodeById.get(childId)
      if (!child || !isGraphScopeDisplayNode(child)) return
      seen.add(childId)
      displayChildren.push(childId)
    }
    const addTocChildAsScope = (childId: string) => {
      const canonicalChapterId = canonicalChapterForToc(childId)
      add(canonicalChapterId || childId)
    }

    if (node?.id === "toc::root") {
      directChildren.forEach((childId) => {
        if (isTocPartNode(nodeById.get(childId))) add(childId)
      })
      return displayChildren.sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
    }

    if (isTocPartNode(node)) {
      directChildren.forEach((childId) => {
        add(canonicalChapterForToc(childId) || (isCanonicalChapterNode(nodeById.get(childId)) ? childId : ""))
      })
      if (displayChildren.length) return displayChildren.sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
      directChildren.forEach((childId) => {
        const child = nodeById.get(childId)
        if (!child) return
        if (isTocChapterScopeNode(child) && (tocEntryType(child) === "chapter" || hasCanonicalChapterChild(childId, rawChildrenByParent, nodeById))) {
          addTocChildAsScope(childId)
          return
        }
        if (hasCanonicalChapterChild(childId, rawChildrenByParent, nodeById)) {
          addTocChildAsScope(childId)
          return
        }
        if (isCanonicalChapterNode(child)) add(childId)
      })
      return displayChildren.sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
    }

    if (isTocChapterScopeNode(node) || hasCanonicalChapterChild(id, rawChildrenByParent, nodeById)) {
      const canonicalChapterId = canonicalChapterForToc(id)
      if (canonicalChapterId) {
        displayChildrenFor(canonicalChapterId).forEach(add)
        return displayChildren.sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
      }
      directChildren.forEach((childId) => {
        const child = nodeById.get(childId)
        if (child && isTocSectionNode(child)) add(childId)
      })
      return displayChildren.sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
    }

    if (isCanonicalChapterNode(node)) {
      directChildren.forEach((childId) => {
        const child = nodeById.get(childId)
        if (child && (isHeadingNode(child) || isKnowledgeContentNode(child))) add(childId)
      })
      return displayChildren.sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
    }

    if (isHeadingNode(node)) {
      directChildren.forEach((childId) => {
        const child = nodeById.get(childId)
        if (child && (isHeadingNode(child) || isKnowledgeContentNode(child))) add(childId)
      })
      return displayChildren.sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
    }

    directChildren.forEach((childId) => {
      add(childId)
    })
    return displayChildren.sort((a, b) => compareGraphScopeNodes(nodeById.get(a), nodeById.get(b)))
  }

  const build = (id: string, ancestors = new Set<string>()): GraphScopeTreeNode | null => {
    if (ancestors.has(id)) return null
    const node = nodeById.get(id)
    if (!node) return null
    const nextAncestors = new Set(ancestors)
    nextAncestors.add(id)
    const children = displayChildrenFor(id)
      .map((childId) => build(childId, nextAncestors))
      .filter(Boolean) as GraphScopeTreeNode[]
    const displayType = graphScopeDisplayType(node, rawChildrenByParent, nodeById)
    const haystack = `${node.label} ${displayType} ${node.content || ""}`.toLowerCase()
    const selfMatch = !term || haystack.includes(term)
    const descendantMatch = children.some((child) => child.match)
    if (term && !selfMatch && !descendantMatch) return null
    return {
      id,
      label: node.label || id,
      type: displayType,
      children,
      match: selfMatch || descendantMatch,
    }
  }

  const roots = rootIds.map((id) => build(id)).filter(Boolean) as GraphScopeTreeNode[]
  if (roots.length) return roots
  return nodes
    .filter((node) => isGraphScopeDisplayNode(node))
    .sort((a, b) => compareGraphScopeNodes(a, b))
    .slice(0, 80)
    .map((node) => ({ id: node.id, label: node.label || node.id, type: graphScopeDisplayType(node, rawChildrenByParent, nodeById), children: [], match: true }))
}

export function buildParentByChild(tree: GraphScopeTreeNode[]) {
  const parentByChild = new Map<string, string>()
  const visit = (node: GraphScopeTreeNode) => {
    node.children.forEach((child) => {
      parentByChild.set(child.id, node.id)
      visit(child)
    })
  }
  tree.forEach(visit)
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
  if (node?.id === "toc::root") return "0|toc-root"
  const metadata = node?.metadata || {}
  const tocPage = Number(metadata.toc_page || 0)
  if (tocPage > 0 || metadata.toc_node_id) {
    const tocLevel = Number(metadata.toc_level || 0)
    const tocNodeId = String(metadata.toc_node_id || node?.id || "")
    return `1|toc|${String(tocPage).padStart(5, "0")}|${String(tocLevel).padStart(2, "0")}|${tocNodeId}`
  }
  const chapter = String(metadata.chapter || node?.id || "")
  const chapterRank = graphScopeChapterRank(chapter, node?.label || "")
  const sourceUnit = String(metadata.source_unit || metadata.source || "")
  const blockIndex = Number(metadata.block_index || 0)
  const partId = String(metadata.book_part_id || "")
  const partRank = partId ? partId.replace("part::appendices", "part::999") : ""
  const typeRank = node?.type === "part" ? 0 : node?.type === "chapter" ? 1 : node?.type === "appendix" ? 1 : node?.type === "section" ? 2 : 3
  if (partRank) return `2|${partRank}|${chapterRank}|${typeRank}|${sourceUnit}|${String(blockIndex).padStart(5, "0")}|${node?.label || ""}`
  return `3|${chapterRank}|${typeRank}|${sourceUnit}|${String(blockIndex).padStart(5, "0")}|${node?.label || ""}`
}

function graphScopeChapterRank(chapter: string, label: string) {
  const normalized = chapter.toLowerCase()
  const appendixMatch = /^appendix(\d+)$/.exec(normalized) || /^appendix\s+(\d+)/i.exec(label)
  if (appendixMatch) return `appendix|${appendixMatch[1].padStart(4, "0")}`
  const chapterMatch = /^chapter(\d+)$/.exec(normalized) || /^chapter\s+(\d+)/i.exec(label)
  if (chapterMatch) return `chapter|${chapterMatch[1].padStart(4, "0")}`
  return `other|${chapter || label}`
}

function isGraphScopeDisplayNode(node?: GraphNode) {
  if (!node) return false
  if (node.id === "toc::root") return true
  if (isTocPartNode(node) || isTocChapterScopeNode(node) || isTocSectionNode(node)) return true
  if (isCanonicalChapterNode(node)) return true
  return isHeadingNode(node) || isKnowledgeContentNode(node)
}

function isTocEntryNode(node?: GraphNode) {
  const metadata = node?.metadata || {}
  return Boolean(node?.id?.startsWith("toc::") || String(metadata.role || "") === "toc_entry")
}

function tocEntryType(node?: GraphNode) {
  return String(node?.metadata?.toc_entry_type || "").toLowerCase()
}

function isTocPartNode(node?: GraphNode) {
  return isTocEntryNode(node) && (tocEntryType(node) === "part" || node?.type === "part")
}

function isTocChapterScopeNode(node?: GraphNode) {
  if (!isTocEntryNode(node)) return false
  const entryType = tocEntryType(node)
  if (HIDDEN_TOC_ENTRY_TYPES.has(entryType)) return false
  return entryType === "chapter" || entryType === "appendix"
}

function isTocSectionNode(node?: GraphNode) {
  if (!isTocEntryNode(node)) return false
  const entryType = tocEntryType(node)
  if (HIDDEN_TOC_ENTRY_TYPES.has(entryType)) return false
  return entryType === "section" || entryType === "subsection"
}

function isCanonicalChapterNode(node?: GraphNode) {
  const role = String(node?.metadata?.role || "")
  return role === "chapter_root" && (node?.type === "chapter" || node?.type === "appendix")
}

function isHeadingNode(node?: GraphNode) {
  return node?.type === "section" && String(node.metadata?.role || "") === "heading"
}

function isKnowledgeContentNode(node?: GraphNode) {
  if (!node) return false
  const nodeType = String(node.type || "")
  return [
    "discussion",
    "proposition",
    "derivation",
    "definition",
    "formula",
    "note",
    "table",
    "figure",
    "example",
    "concept",
  ].includes(nodeType)
}

function canonicalChapterChildren(parentId: string, childrenByParent: Map<string, string[]>, nodeById: Map<string, GraphNode>) {
  return (childrenByParent.get(parentId) || []).filter((childId) => isCanonicalChapterNode(nodeById.get(childId)))
}

function hasCanonicalChapterChild(parentId: string, childrenByParent: Map<string, string[]>, nodeById: Map<string, GraphNode>) {
  return canonicalChapterChildren(parentId, childrenByParent, nodeById).length > 0
}

function graphScopeDisplayType(node: GraphNode, childrenByParent: Map<string, string[]>, nodeById: Map<string, GraphNode>) {
  if (node.id === "toc::root") return "part"
  if (isTocEntryNode(node)) {
    const entryType = tocEntryType(node)
    if (entryType === "part") return "part"
    if (entryType === "section" || entryType === "subsection") {
      const canonicalChild = canonicalChapterChildren(node.id, childrenByParent, nodeById)[0]
      const canonicalNode = canonicalChild ? nodeById.get(canonicalChild) : undefined
      if (canonicalNode?.type === "chapter" || canonicalNode?.type === "appendix") return canonicalNode.type
      return "section"
    }
    if (entryType === "chapter" || entryType === "appendix") {
      const canonicalChild = canonicalChapterChildren(node.id, childrenByParent, nodeById)[0]
      const canonicalNode = canonicalChild ? nodeById.get(canonicalChild) : undefined
      if (canonicalNode?.type === "chapter" || canonicalNode?.type === "appendix") return canonicalNode.type
      return entryType === "appendix" ? "appendix" : "chapter"
    }
  }
  return node.type || "concept"
}

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    part: "篇章",
    chapter: "章节",
    appendix: "附录",
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
