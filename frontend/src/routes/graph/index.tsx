import { createFileRoute, Link } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useState } from "react"
import { Background, Controls, MiniMap, ReactFlow, ReactFlowProvider, type Edge, type Node, useReactFlow } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import {
  BookOpen,
  ExternalLink,
  Focus,
  GitBranch,
  Info,
  Layers,
  Network,
  RotateCcw,
  Save,
  Search,
  Sparkles,
  Waypoints,
} from "lucide-react"
import { useGraphNodes, useGraphRelationships, useGraphStats } from "@/api/graph"
import { useUpdateNode } from "@/api/maintenance"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import { layoutGraphNodes, type GraphLayoutMode } from "@/lib/graphLayout"
import { useAuth } from "@/hooks/useAuth"
import type { GraphNode, GraphRelation } from "@/types/graph"

export const Route = createFileRoute("/graph/")({
  component: GraphPage,
})

type GraphViewMode = "explore" | "chapterPath" | "prerequisites" | "formulaTheorem" | "overview"

interface RelationBuckets {
  incoming: GraphRelation[]
  outgoing: GraphRelation[]
  related: GraphRelation[]
  formulas: GraphRelation[]
  examples: GraphRelation[]
}

const nodeColors: Record<string, string> = {
  chapter: "#2563eb",
  concept: "#16a34a",
  formula: "#9333ea",
  theorem: "#dc2626",
  example: "#ea580c",
  observation: "#0891b2",
  note: "#64748b",
}

const viewModes: Array<{ id: GraphViewMode; label: string; icon: React.ReactNode }> = [
  { id: "explore", label: "探索布局", icon: <Sparkles size={15} /> },
  { id: "chapterPath", label: "章节路径", icon: <BookOpen size={15} /> },
  { id: "prerequisites", label: "前置知识", icon: <GitBranch size={15} /> },
  { id: "formulaTheorem", label: "公式定理", icon: <Layers size={15} /> },
  { id: "overview", label: "全图概览", icon: <Network size={15} /> },
]

const layoutModes: Array<{ id: GraphLayoutMode; label: string }> = [
  { id: "elk", label: "ELK 分层" },
  { id: "dagre", label: "Dagre 快速" },
  { id: "grid", label: "网格备用" },
]

const DEFAULT_TYPE = "all"
const DEFAULT_RELATION = "all"
const RECOMMENDED_LIMIT = 32
const FOCUSED_LIMIT = 82
const OVERVIEW_LIMIT = 360
const LIMITED_NODE_FETCH_LIMIT = 1200
const LIMITED_RELATION_FETCH_LIMIT = 3600
const ALL_NODE_FETCH_LIMIT = 10000
const ALL_RELATION_FETCH_LIMIT = 50000

function GraphPage() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canEditGraph = user?.role === "teacher"
  const [searchTerm, setSearchTerm] = useState("")
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [nodeType, setNodeType] = useState(DEFAULT_TYPE)
  const [relationType, setRelationType] = useState(DEFAULT_RELATION)
  const [viewMode, setViewMode] = useState<GraphViewMode>("explore")
  const [layoutMode, setLayoutMode] = useState<GraphLayoutMode>("elk")
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set())
  const [flowNodes, setFlowNodes] = useState<Node[]>([])
  const [layoutStatus, setLayoutStatus] = useState("")
  const [editMessage, setEditMessage] = useState("")

  const showAllNodes = viewMode === "overview"
  const { data: nodesData, isLoading: nodesLoading } = useGraphNodes(showAllNodes ? ALL_NODE_FETCH_LIMIT : LIMITED_NODE_FETCH_LIMIT)
  const { data: relationshipsData, isLoading: relationshipsLoading } = useGraphRelationships(showAllNodes ? ALL_RELATION_FETCH_LIMIT : LIMITED_RELATION_FETCH_LIMIT)
  const { data: statsData } = useGraphStats()
  const updateNode = useUpdateNode()

  const rawNodes = useMemo(() => nodesData?.nodes || [], [nodesData?.nodes])
  const rawRelationships = useMemo(() => relationshipsData?.relationships || [], [relationshipsData?.relationships])
  const stats = statsData?.data
  const nodeById = useMemo(() => new Map(rawNodes.map((node) => [node.id, node])), [rawNodes])
  const degreeById = useMemo(() => buildDegreeMap(rawRelationships), [rawRelationships])

  const nodeTypes = useMemo(() => unique(rawNodes.map((node) => node.type || "concept")), [rawNodes])
  const relationTypes = useMemo(
    () => unique(rawRelationships.map((relation) => relation.relation_type || "related")),
    [rawRelationships],
  )

  const baseFilteredNodes = useMemo(() => {
    const term = searchTerm.trim().toLowerCase()
    return rawNodes.filter((node) => {
      if (nodeType !== DEFAULT_TYPE && (node.type || "concept") !== nodeType) return false
      if (!term) return true
      const haystack = `${node.label} ${node.type} ${node.content || ""}`.toLowerCase()
      return haystack.includes(term)
    })
  }, [rawNodes, searchTerm, nodeType])

  const filteredNodeIds = useMemo(() => new Set(baseFilteredNodes.map((node) => node.id)), [baseFilteredNodes])
  const relationBuckets = useMemo(
    () => getRelationBuckets(selectedNodeId, rawRelationships, nodeById, relationType),
    [nodeById, rawRelationships, relationType, selectedNodeId],
  )
  const selectedNeighborIds = useMemo(() => getNeighborIds(selectedNodeId, rawRelationships, relationType), [rawRelationships, relationType, selectedNodeId])
  const recommendedNodes = useMemo(() => getRecommendedStarts(baseFilteredNodes, degreeById), [baseFilteredNodes, degreeById])

  useEffect(() => {
    if (!selectedNodeId && recommendedNodes[0]) {
      setSelectedNodeId(recommendedNodes[0].id)
    }
  }, [recommendedNodes, selectedNodeId])

  const visibleNodes = useMemo(() => {
    if (viewMode === "overview") {
      return baseFilteredNodes.slice(0, OVERVIEW_LIMIT)
    }

    if (!selectedNodeId) {
      return recommendedNodes.slice(0, RECOMMENDED_LIMIT)
    }

    const visibleIds = new Set<string>([selectedNodeId, ...expandedNodeIds])
    if (viewMode === "explore") {
      recommendedNodes.slice(0, 12).forEach((node) => visibleIds.add(node.id))
      selectedNeighborIds.forEach((id) => visibleIds.add(id))
    }
    if (viewMode === "chapterPath") {
      addTypedNodes(visibleIds, baseFilteredNodes, ["chapter"], degreeById, 40)
      relationBuckets.incoming.concat(relationBuckets.outgoing).forEach((relation) => {
        visibleIds.add(relation.source_id)
        visibleIds.add(relation.target_id)
      })
    }
    if (viewMode === "prerequisites") {
      relationBuckets.incoming.concat(relationBuckets.related.slice(0, 16)).forEach((relation) => {
        visibleIds.add(relation.source_id)
        visibleIds.add(relation.target_id)
      })
    }
    if (viewMode === "formulaTheorem") {
      relationBuckets.formulas.concat(relationBuckets.examples).forEach((relation) => {
        visibleIds.add(relation.source_id)
        visibleIds.add(relation.target_id)
      })
      addTypedNodes(visibleIds, baseFilteredNodes, ["formula", "theorem", "example"], degreeById, 42)
    }

    selectedNeighborIds.forEach((id) => {
      if (visibleIds.size < FOCUSED_LIMIT) visibleIds.add(id)
    })

    return baseFilteredNodes
      .filter((node) => visibleIds.has(node.id) && filteredNodeIds.has(node.id))
      .sort((a, b) => getNodeScore(b, degreeById) - getNodeScore(a, degreeById))
      .slice(0, FOCUSED_LIMIT)
  }, [
    baseFilteredNodes,
    degreeById,
    expandedNodeIds,
    filteredNodeIds,
    recommendedNodes,
    relationBuckets,
    selectedNeighborIds,
    selectedNodeId,
    viewMode,
  ])

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes])
  const visibleRelationships = useMemo(
    () =>
      rawRelationships.filter((relation) => {
        if (relationType !== DEFAULT_RELATION && (relation.relation_type || "related") !== relationType) return false
        return visibleNodeIds.has(relation.source_id) && visibleNodeIds.has(relation.target_id)
      }),
    [rawRelationships, relationType, visibleNodeIds],
  )

  const highlightedIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>()
    return new Set([selectedNodeId, ...selectedNeighborIds])
  }, [selectedNeighborIds, selectedNodeId])

  const baseFlowNodes = useMemo<Node[]>(
    () => visibleNodes.map((node) => createFlowNode(node, highlightedIds, selectedNodeId)),
    [highlightedIds, selectedNodeId, visibleNodes],
  )
  const flowEdges = useMemo<Edge[]>(
    () => createFlowEdges(visibleRelationships, selectedNodeId),
    [selectedNodeId, visibleRelationships],
  )

  useEffect(() => {
    let cancelled = false
    setLayoutStatus(layoutMode === "elk" ? "正在计算 ELK 布局..." : layoutMode === "dagre" ? "正在计算 Dagre 布局..." : "")
    layoutGraphNodes(baseFlowNodes, flowEdges, {
      mode: layoutMode,
      direction: viewMode === "chapterPath" ? "DOWN" : "RIGHT",
      nodeWidth: 220,
      nodeHeight: 70,
    }).then((nodes) => {
      if (cancelled) return
      setFlowNodes(nodes)
      setLayoutStatus("")
    })
    return () => {
      cancelled = true
    }
  }, [baseFlowNodes, flowEdges, layoutMode, viewMode])

  const selectedNode = selectedNodeId ? nodeById.get(selectedNodeId) : recommendedNodes[0]
  const isLoading = nodesLoading || relationshipsLoading
  const hiddenCount = Math.max(0, baseFilteredNodes.length - visibleNodes.length)

  const handleSaveNode = async (nodeId: string, content: string) => {
    setEditMessage("")
    const result = await updateNode.mutateAsync({ node_id: nodeId, content })
    if (result.success) {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["graph-nodes"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-relationships"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-stats"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-data"] }),
        queryClient.invalidateQueries({ queryKey: ["maintenance-graph"] }),
      ])
      setEditMessage("已保存")
    }
  }

  const startFromNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId)
    setViewMode("explore")
    setExpandedNodeIds(new Set())
    setEditMessage("")
  }, [])

  const expandSelected = useCallback(() => {
    if (!selectedNodeId) return
    setExpandedNodeIds((prev) => new Set([...prev, selectedNodeId, ...selectedNeighborIds]))
  }, [selectedNeighborIds, selectedNodeId])

  const resetToFocus = useCallback(() => {
    setExpandedNodeIds(new Set())
    setViewMode("explore")
  }, [])

  const backToStarts = useCallback(() => {
    setSelectedNodeId(recommendedNodes[0]?.id || null)
    setExpandedNodeIds(new Set())
    setViewMode("explore")
  }, [recommendedNodes])

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold">知识图谱</h1>
          <p className="text-muted-foreground">从推荐起点进入，围绕章节、前置知识和公式定理逐步展开。</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              type="text"
              placeholder="搜索节点、类型或内容..."
              className="w-full rounded-lg border bg-background py-2 pl-9 pr-4 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 sm:w-72"
            />
          </div>
          {canEditGraph && (
            <Link
              to="/graph/admin"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <ExternalLink size={16} />
              图谱管理
            </Link>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="总节点" value={stats?.total_nodes ?? rawNodes.length} />
        <StatCard label="总关系" value={stats?.total_relationships ?? rawRelationships.length} />
        <StatCard label="当前节点" value={visibleNodes.length} />
        <StatCard label="当前关系" value={visibleRelationships.length} />
      </div>

      <div className="rounded-lg border bg-card">
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          {viewModes.map((mode) => (
            <button key={mode.id} type="button" onClick={() => setViewMode(mode.id)} className={cnSegment(viewMode === mode.id)}>
              {mode.icon}
              {mode.label}
            </button>
          ))}
          <div className="flex w-full flex-wrap items-center gap-2 lg:ml-auto lg:w-auto">
            <SelectFilter label="节点" value={nodeType} onChange={setNodeType} options={nodeTypes} allLabel="全部" />
            <SelectFilter label="关系" value={relationType} onChange={setRelationType} options={relationTypes} allLabel="全部" />
            <SelectFilter label="布局" value={layoutMode} onChange={(value) => setLayoutMode(value as GraphLayoutMode)} options={layoutModes.map((mode) => mode.id)} labels={Object.fromEntries(layoutModes.map((mode) => [mode.id, mode.label]))} allLabel="" hideAll />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 p-3">
          <button type="button" onClick={expandSelected} disabled={!selectedNodeId} className="inline-flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm hover:bg-muted disabled:opacity-50">
            <Waypoints size={16} />
            展开邻居
          </button>
          <button type="button" onClick={resetToFocus} disabled={!selectedNodeId} className="inline-flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm hover:bg-muted disabled:opacity-50">
            <Focus size={16} />
            收起到焦点
          </button>
          <button type="button" onClick={backToStarts} className="inline-flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm hover:bg-muted">
            <Sparkles size={16} />
            回到起点
          </button>
          {hiddenCount > 0 && <span className="text-sm text-muted-foreground">当前视图收起 {hiddenCount} 个节点，可搜索、切换模式或进入全图概览。</span>}
          {viewMode === "overview" && <span className="text-sm text-amber-600">全图概览最多显示 {OVERVIEW_LIMIT} 个节点，大图渲染可能较慢。</span>}
        </div>
      </div>

      <div className="grid min-h-[460px] grid-cols-1 gap-5 xl:min-h-[720px] xl:grid-cols-[minmax(0,1fr)_390px]">
        <section className="overflow-hidden rounded-lg border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
            <h2 className="flex items-center gap-2 font-semibold">
              <Network size={18} />
              图谱可视化
            </h2>
            <span className="text-xs text-muted-foreground">
              {layoutStatus || `${visibleNodes.length} nodes / ${visibleRelationships.length} edges`}
            </span>
          </div>
          <ReactFlowProvider>
            <GraphCanvas
              isLoading={isLoading}
              nodes={flowNodes}
              edges={flowEdges}
              onSelectNode={(nodeId) => {
                setSelectedNodeId(nodeId)
                setEditMessage("")
              }}
            />
          </ReactFlowProvider>
        </section>

        <aside className="max-h-none overflow-auto rounded-lg border bg-card xl:max-h-[720px]">
          <div className="sticky top-0 z-10 border-b bg-card p-4">
            <h2 className="flex items-center gap-2 font-semibold">
              <Info size={18} />
              节点详情
            </h2>
          </div>
          {selectedNode ? (
            <NodeDetails
              node={selectedNode}
              isSaving={updateNode.isPending}
              saveMessage={editMessage}
              canEdit={canEditGraph}
              onSave={handleSaveNode}
              onStart={() => startFromNode(selectedNode.id)}
              incoming={relationBuckets.incoming}
              outgoing={relationBuckets.outgoing}
              formulas={relationBuckets.formulas}
              examples={relationBuckets.examples}
              nodeById={nodeById}
            />
          ) : (
            <div className="p-6 text-sm text-muted-foreground">选择一个推荐起点查看学习建议。</div>
          )}
        </aside>
      </div>
    </div>
  )
}

function GraphCanvas({
  isLoading,
  nodes,
  edges,
  onSelectNode,
}: {
  isLoading: boolean
  nodes: Node[]
  edges: Edge[]
  onSelectNode: (nodeId: string) => void
}) {
  const { fitView } = useReactFlow()

  useEffect(() => {
    if (nodes.length) {
      window.requestAnimationFrame(() => fitView({ padding: 0.18, duration: 220 }))
    }
  }, [fitView, nodes])

  return (
    <div className="h-[460px] bg-slate-50 sm:h-[560px] xl:h-[660px]">
      {isLoading ? (
        <div className="flex h-full items-center justify-center">
          <LoadingSpinner text="加载图谱中..." />
        </div>
      ) : nodes.length === 0 ? (
        <div className="flex h-full items-center justify-center p-8">
          <EmptyState title="暂无图谱节点" description="当前筛选条件下没有可展示的数据。" />
        </div>
      ) : (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          minZoom={0.08}
          maxZoom={1.8}
          onNodeClick={(_, node) => onSelectNode(node.id)}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
        >
          <Background color="#cbd5e1" gap={36} />
          <Controls />
          <MiniMap className="hidden sm:block" pannable zoomable nodeColor={(node) => String(node.data?.color || "#64748b")} />
          <FitViewButton />
        </ReactFlow>
      )}
    </div>
  )
}

function FitViewButton() {
  const { fitView } = useReactFlow()
  return (
    <button
      type="button"
      onClick={() => fitView({ padding: 0.18, duration: 220 })}
      className="absolute right-3 top-3 z-10 inline-flex items-center gap-2 rounded-lg border bg-white px-2.5 py-2 text-sm shadow-sm hover:bg-slate-50 sm:px-3"
    >
      <RotateCcw size={15} />
      重置视图
    </button>
  )
}

function createFlowNode(node: GraphNode, highlightedIds: Set<string>, selectedNodeId: string | null): Node {
  const type = node.type || "concept"
  const color = nodeColors[type] || "#0f766e"
  const isSelected = node.id === selectedNodeId
  const isHighlighted = highlightedIds.size === 0 || highlightedIds.has(node.id)
  return {
    id: node.id,
    position: { x: 0, y: 0 },
    data: {
      label: truncateLabel(node.label || node.id),
      color,
    },
    style: {
      width: 220,
      height: 70,
      borderRadius: 8,
      border: `1px solid ${isSelected ? "#0f172a" : color}`,
      background: isHighlighted ? "#ffffff" : "#f8fafc",
      color: "#0f172a",
      opacity: isHighlighted ? 1 : 0.42,
      boxShadow: isSelected ? "0 0 0 3px rgba(37, 99, 235, 0.22)" : "0 4px 14px rgba(15, 23, 42, 0.08)",
      fontSize: 12,
      lineHeight: 1.35,
      padding: "10px 12px",
    },
  }
}

function createFlowEdges(relations: GraphRelation[], selectedNodeId: string | null): Edge[] {
  return relations.map((relation, index) => {
    const isFocused = !!selectedNodeId && (relation.source_id === selectedNodeId || relation.target_id === selectedNodeId)
    return {
      id: relation.id || `${relation.source_id}-${relation.target_id}-${index}`,
      source: relation.source_id,
      target: relation.target_id,
      label: isFocused ? relation.relation_type : undefined,
      type: "smoothstep",
      animated: isFocused,
      style: {
        stroke: isFocused ? "#2563eb" : "#94a3b8",
        strokeWidth: isFocused ? 2.4 : 1.1,
        opacity: selectedNodeId ? (isFocused ? 1 : 0.24) : 0.64,
      },
      labelStyle: { fill: "#1d4ed8", fontSize: 11, fontWeight: 600 },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.92 },
    }
  })
}

function NodeDetails({
  node,
  isSaving,
  saveMessage,
  canEdit,
  onSave,
  onStart,
  incoming,
  outgoing,
  formulas,
  examples,
  nodeById,
}: {
  node: GraphNode
  isSaving: boolean
  saveMessage: string
  canEdit: boolean
  onSave: (nodeId: string, content: string) => Promise<void>
  onStart: () => void
  incoming: GraphRelation[]
  outgoing: GraphRelation[]
  formulas: GraphRelation[]
  examples: GraphRelation[]
  nodeById: Map<string, GraphNode>
}) {
  const [draftContent, setDraftContent] = useState(node.content || "")

  useEffect(() => {
    setDraftContent(node.content || "")
  }, [node.id, node.content])

  const prerequisites = incoming.map((relation) => nodeById.get(relation.source_id)).filter(Boolean) as GraphNode[]
  const nextNodes = outgoing.map((relation) => nodeById.get(relation.target_id)).filter(Boolean) as GraphNode[]

  return (
    <div className="space-y-4 p-4">
      <div>
        <div className="text-xs font-medium uppercase text-muted-foreground">名称</div>
        <div className="mt-1 text-lg font-semibold">{node.label || node.id}</div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Badge>{node.type || "concept"}</Badge>
        {node.source && <Badge>{node.source}</Badge>}
        {typeof node.confidence === "number" && <Badge>置信度 {node.confidence.toFixed(2)}</Badge>}
      </div>
      <button
        type="button"
        onClick={onStart}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        <Focus size={15} />
        从这里开始
      </button>

      <section className="rounded-lg border bg-muted/40 p-3">
        <h3 className="mb-2 text-sm font-semibold">学习建议</h3>
        <div className="space-y-2 text-sm text-muted-foreground">
          <p>{buildLearningAdvice(node, prerequisites.length, nextNodes.length, formulas.length)}</p>
          <RelationList title="前置知识" nodes={prerequisites.slice(0, 5)} empty="暂无明确前置节点" />
          <RelationList title="下一步节点" nodes={nextNodes.slice(0, 5)} empty="暂无明确后续节点" />
          <RelationList title="相关公式/定理/例题" nodes={relationsToNodes(formulas.concat(examples), nodeById, node.id).slice(0, 6)} empty="暂无相关公式或例题" />
        </div>
      </section>

      <div>
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="text-xs font-medium uppercase text-muted-foreground">内容</div>
          {saveMessage && <span className="text-xs text-emerald-600">{saveMessage}</span>}
        </div>
        {canEdit ? (
          <>
            <textarea
              value={draftContent}
              onChange={(event) => setDraftContent(event.target.value)}
              className="min-h-[160px] w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm leading-relaxed focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
            <button
              type="button"
              onClick={() => onSave(node.id, draftContent)}
              disabled={isSaving || draftContent === (node.content || "")}
              className="mt-2 inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {isSaving ? <LoadingSpinner size={14} /> : <Save size={14} />}
              {isSaving ? "保存中..." : "保存节点内容"}
            </button>
          </>
        ) : (
          <div className="rounded-lg border bg-background p-3 text-sm leading-relaxed">
            <RichTextContent content={draftContent || "暂无描述"} />
          </div>
        )}
        {canEdit && (
          <div className="mt-3 max-h-[220px] overflow-auto rounded-lg bg-muted p-3 text-sm leading-relaxed">
            <RichTextContent content={draftContent || "暂无描述"} />
          </div>
        )}
      </div>
      {canEdit && node.metadata && Object.keys(node.metadata).length > 0 && (
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">元数据</div>
          <pre className="max-h-[220px] overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
            {JSON.stringify(node.metadata, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

function RelationList({ title, nodes, empty }: { title: string; nodes: GraphNode[]; empty: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-foreground">{title}</div>
      {nodes.length ? (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {nodes.map((node) => (
            <span key={node.id} className="rounded-md border bg-background px-2 py-1 text-xs text-foreground">
              {truncateLabel(node.label || node.id, 28)}
            </span>
          ))}
        </div>
      ) : (
        <div className="mt-1 text-xs">{empty}</div>
      )}
    </div>
  )
}

function SelectFilter({
  label,
  value,
  options,
  labels,
  allLabel,
  hideAll,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  labels?: Record<string, string>
  allLabel: string
  hideAll?: boolean
  onChange: (value: string) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="rounded-lg border bg-background px-3 py-2">
        {!hideAll && <option value="all">{allLabel}</option>}
        {options.map((option) => (
          <option key={option} value={option}>
            {labels?.[option] || option}
          </option>
        ))}
      </select>
    </label>
  )
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border bg-background px-2.5 py-1 text-xs text-muted-foreground">{children}</span>
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  )
}

function getNeighborIds(selectedNodeId: string | null, relations: GraphRelation[], relationType: string) {
  const ids = new Set<string>()
  if (!selectedNodeId) return ids
  relations.forEach((relation) => {
    if (relationType !== DEFAULT_RELATION && (relation.relation_type || "related") !== relationType) return
    if (relation.source_id === selectedNodeId) ids.add(relation.target_id)
    if (relation.target_id === selectedNodeId) ids.add(relation.source_id)
  })
  return ids
}

function getRelationBuckets(selectedNodeId: string | null, relations: GraphRelation[], nodeById: Map<string, GraphNode>, relationType: string): RelationBuckets {
  const buckets: RelationBuckets = { incoming: [], outgoing: [], related: [], formulas: [], examples: [] }
  if (!selectedNodeId) return buckets
  relations.forEach((relation) => {
    if (relationType !== DEFAULT_RELATION && (relation.relation_type || "related") !== relationType) return
    const touchesSelected = relation.source_id === selectedNodeId || relation.target_id === selectedNodeId
    if (!touchesSelected) return
    if (relation.target_id === selectedNodeId) buckets.incoming.push(relation)
    if (relation.source_id === selectedNodeId) buckets.outgoing.push(relation)
    buckets.related.push(relation)
    const otherNode = nodeById.get(relation.source_id === selectedNodeId ? relation.target_id : relation.source_id)
    if (["formula", "theorem"].includes(otherNode?.type || "")) buckets.formulas.push(relation)
    if ((otherNode?.type || "") === "example") buckets.examples.push(relation)
  })
  return buckets
}

function getRecommendedStarts(nodes: GraphNode[], degreeById: Map<string, number>) {
  return [...nodes]
    .sort((a, b) => getNodeScore(b, degreeById) - getNodeScore(a, degreeById))
    .slice(0, RECOMMENDED_LIMIT)
}

function getNodeScore(node: GraphNode, degreeById: Map<string, number>) {
  const typeWeight: Record<string, number> = {
    chapter: 1000,
    concept: 650,
    theorem: 420,
    formula: 390,
    example: 180,
  }
  return (typeWeight[node.type || "concept"] || 260) + (degreeById.get(node.id) || 0) * 18
}

function buildDegreeMap(relations: GraphRelation[]) {
  const map = new Map<string, number>()
  relations.forEach((relation) => {
    map.set(relation.source_id, (map.get(relation.source_id) || 0) + 1)
    map.set(relation.target_id, (map.get(relation.target_id) || 0) + 1)
  })
  return map
}

function addTypedNodes(target: Set<string>, nodes: GraphNode[], types: string[], degreeById: Map<string, number>, limit: number) {
  nodes
    .filter((node) => types.includes(node.type || "concept"))
    .sort((a, b) => getNodeScore(b, degreeById) - getNodeScore(a, degreeById))
    .slice(0, limit)
    .forEach((node) => target.add(node.id))
}

function relationsToNodes(relations: GraphRelation[], nodeById: Map<string, GraphNode>, selectedNodeId: string) {
  const nodes: GraphNode[] = []
  const seen = new Set<string>()
  relations.forEach((relation) => {
    const id = relation.source_id === selectedNodeId ? relation.target_id : relation.source_id
    const node = nodeById.get(id)
    if (node && !seen.has(node.id)) {
      seen.add(node.id)
      nodes.push(node)
    }
  })
  return nodes
}

function buildLearningAdvice(node: GraphNode, prereqCount: number, nextCount: number, relatedCount: number) {
  if ((node.type || "") === "chapter") {
    return prereqCount
      ? `这是章节节点，建议先补齐 ${prereqCount} 个前置节点，再沿 ${nextCount || "后续"} 个节点继续。`
      : "这是合适的章节起点，可先通读内容，再展开概念、公式和例题。"
  }
  if (["formula", "theorem"].includes(node.type || "")) {
    return `先确认符号含义和适用条件，再通过 ${relatedCount || "相关"} 个例题或章节节点巩固。`
  }
  return nextCount ? `先理解当前概念，再顺着 ${nextCount} 个后续节点建立知识链。` : "适合作为局部复习点，可展开邻居查看上下文。"
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b))
}

function truncateLabel(value: string, maxLength = 42) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value
}

function cnSegment(active: boolean) {
  return [
    "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors hover:bg-muted",
    active ? "border-primary/30 bg-primary/10 text-primary" : "bg-background",
  ].join(" ")
}
