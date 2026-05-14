import { createFileRoute, Link } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, ReactFlowProvider, getSimpleBezierPath, type Edge, type Node, type NodeProps, useUpdateNodeInternals } from "@xyflow/react"
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
import { useGraphNodes, useGraphRelations, useGraphRelationships, useGraphStats } from "@/api/graph"
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
type FlowNodeData = {
  label: string
  color: string
}

interface GraphSubgraph {
  nodes: GraphNode[]
  relationships: GraphRelation[]
  anchorNodeId: string | null
}

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

const graphNodeTypes = {
  knowledge: KnowledgeFlowNode,
}

const DEFAULT_TYPE = "all"
const DEFAULT_RELATION = "all"
const FLOW_NODE_WIDTH = 220
const FLOW_NODE_HEIGHT = 70
const FLOW_HANDLE_SIZE = 8
const RECOMMENDED_LIMIT = 32
const FOCUSED_LIMIT = 82
const OVERVIEW_LIMIT = 360
const FOCUSED_EDGE_LIMIT = 220
const OVERVIEW_EDGE_LIMIT = 1200
const LIMITED_NODE_FETCH_LIMIT = 5000
const LIMITED_RELATION_FETCH_LIMIT = 50000
const ALL_NODE_FETCH_LIMIT = 10000
const ALL_RELATION_FETCH_LIMIT = 50000
const STRUCTURAL_RELATION_TYPES = new Set(["contains"])
const PATH_RELATION_TYPES = new Set(["precedes"])
const FORMULA_RELATION_TYPES = new Set(["references_formula", "references_table"])
const PREREQUISITE_RELATION_TYPES = new Set(["precedes", "defines", "derives", "explains", "depends_on", "supports", "causes"])
const SEMANTIC_RELATION_TYPES = new Set([
  "precedes",
  "defines",
  "derives",
  "explains",
  "depends_on",
  "example_of",
  "supports",
  "causes",
  "contrasts_with",
  "references_formula",
  "references_table",
])
const FORMULA_CONTEXT_TYPES = new Set(["formula", "theorem", "table", "note"])
const CONTENT_START_TYPES = new Set(["proposition", "derivation", "discussion", "concept"])

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
  const { data: selectedRelationsData } = useGraphRelations(selectedNodeId || "")
  const { data: statsData } = useGraphStats()
  const updateNode = useUpdateNode()

  const rawNodes = useMemo(() => nodesData?.nodes || [], [nodesData?.nodes])
  const selectedRelations = useMemo(
    () => (selectedRelationsData?.nodeId === selectedNodeId ? selectedRelationsData.relations : []),
    [selectedNodeId, selectedRelationsData?.nodeId, selectedRelationsData?.relations],
  )
  const rawRelationships = useMemo(
    () => mergeRelations(relationshipsData?.relationships || [], selectedRelations),
    [relationshipsData?.relationships, selectedRelations],
  )
  const stats = statsData?.data
  const nodeById = useMemo(() => new Map(rawNodes.map((node) => [node.id, node])), [rawNodes])
  const degreeById = useMemo(() => buildDegreeMap(rawRelationships), [rawRelationships])

  const nodeTypes = useMemo(() => unique(rawNodes.map((node) => node.type || "concept")), [rawNodes])
  const relationTypes = useMemo(
    () => unique(rawRelationships.map((relation) => relation.relation_type || "related")),
    [rawRelationships],
  )
  const contentRelations = useMemo(
    () =>
      rawRelationships.filter((relation) => {
        if (isStructuralRelation(relation)) return false
        return nodeById.has(relation.source_id) && nodeById.has(relation.target_id)
      }),
    [nodeById, rawRelationships],
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
  const focusedRelationships = useMemo(
    () => getNodeRelations(selectedNodeId, rawRelationships, relationType),
    [rawRelationships, relationType, selectedNodeId],
  )
  const selectedNeighborIds = useMemo(() => getNeighborIds(selectedNodeId, focusedRelationships), [focusedRelationships, selectedNodeId])
  const recommendedNodes = useMemo(() => getRecommendedStarts(baseFilteredNodes, degreeById, contentRelations), [baseFilteredNodes, contentRelations, degreeById])

  useEffect(() => {
    if (!selectedNodeId && recommendedNodes[0]) {
      setSelectedNodeId(recommendedNodes[0].id)
    }
  }, [recommendedNodes, selectedNodeId])

  const graphSubgraph = useMemo<GraphSubgraph>(() => {
    const filteredRelations = rawRelationships.filter((relation) => {
      if (relationType !== DEFAULT_RELATION && (relation.relation_type || "related") !== relationType) return false
      return nodeById.has(relation.source_id) && nodeById.has(relation.target_id)
    })

    return buildGraphSubgraph({
      viewMode,
      selectedNodeId,
      expandedNodeIds,
      selectedNeighborIds,
      recommendedNodes,
      baseFilteredNodes,
      rawNodes,
      filteredNodeIds,
      filteredRelations,
      contentRelations,
      nodeById,
      degreeById,
      limit: viewMode === "overview" ? OVERVIEW_LIMIT : FOCUSED_LIMIT,
    })
  }, [
    baseFilteredNodes,
    contentRelations,
    degreeById,
    expandedNodeIds,
    filteredNodeIds,
    nodeById,
    rawNodes,
    rawRelationships,
    recommendedNodes,
    relationType,
    selectedNeighborIds,
    selectedNodeId,
    viewMode,
  ])

  const visibleRelationships = graphSubgraph.relationships
  const visibleNodes = graphSubgraph.nodes

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes])
  const renderRelationships = useMemo(
    () =>
      visibleRelationships.filter((relation) => visibleNodeIds.has(relation.source_id) && visibleNodeIds.has(relation.target_id)),
    [visibleNodeIds, visibleRelationships],
  )

  const highlightedIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>()
    return new Set([selectedNodeId, ...(viewMode === "explore" ? selectedNeighborIds : [])])
  }, [selectedNeighborIds, selectedNodeId, viewMode])

  const baseFlowNodes = useMemo<Node[]>(
    () => visibleNodes.map((node) => createFlowNode(node, highlightedIds, selectedNodeId, getLayoutDirection(viewMode))),
    [highlightedIds, selectedNodeId, viewMode, visibleNodes],
  )
  const flowEdges = useMemo<Edge[]>(
    () => createFlowEdges(renderRelationships, selectedNodeId),
    [renderRelationships, selectedNodeId],
  )
  const canvasNodes = useMemo<Node[]>(
    () => (hasSameNodeIds(flowNodes, baseFlowNodes) ? flowNodes : seedFlowNodes(baseFlowNodes, flowNodes)),
    [baseFlowNodes, flowNodes],
  )
  const canvasNodeIds = useMemo(() => new Set(canvasNodes.map((node) => node.id)), [canvasNodes])
  const canvasEdges = useMemo<Edge[]>(
    () => flowEdges.filter((edge) => canvasNodeIds.has(edge.source) && canvasNodeIds.has(edge.target)),
    [canvasNodeIds, flowEdges],
  )
  const hiddenCanvasEdgeCount = flowEdges.length - canvasEdges.length

  useEffect(() => {
    Object.assign(window, {
      __KGTS_GRAPH_DEBUG__: {
        selectedNodeId,
        anchorNodeId: graphSubgraph.anchorNodeId,
        viewMode,
        rawRelationshipPayload: relationshipsData?.rawCount ?? rawRelationships.length,
        missingEndpointRelationships: relationshipsData?.missingEndpointCount ?? 0,
        missingNodeRelationships: relationshipsData?.missingNodeCount ?? 0,
        rawNodes: rawNodes.length,
        rawRelationships: rawRelationships.length,
        contentRelationships: contentRelations.length,
        visibleNodes: visibleNodes.length,
        visibleRelationships: visibleRelationships.length,
        renderRelationships: renderRelationships.length,
        flowNodes: flowNodes.length,
        flowEdges: flowEdges.length,
        canvasNodes: canvasNodes.length,
        canvasEdges: canvasEdges.length,
        hiddenCanvasEdges: hiddenCanvasEdgeCount,
        selectedRelations: focusedRelationships.length,
        selectedNeighbors: selectedNeighborIds.size,
      },
    })
  }, [
    canvasEdges.length,
    canvasNodes.length,
    contentRelations.length,
    flowEdges.length,
    flowNodes.length,
    focusedRelationships.length,
    graphSubgraph.anchorNodeId,
    hiddenCanvasEdgeCount,
    rawNodes.length,
    rawRelationships.length,
    relationshipsData?.missingEndpointCount,
    relationshipsData?.missingNodeCount,
    relationshipsData?.rawCount,
    renderRelationships.length,
    selectedNeighborIds.size,
    selectedNodeId,
    visibleNodes.length,
    visibleRelationships.length,
    viewMode,
  ])

  useEffect(() => {
    let cancelled = false
    setFlowNodes((currentNodes) => seedFlowNodes(baseFlowNodes, currentNodes))
    setLayoutStatus(layoutMode === "elk" ? "正在计算 ELK 布局..." : layoutMode === "dagre" ? "正在计算 Dagre 布局..." : "")
    layoutGraphNodes(baseFlowNodes, flowEdges, {
      mode: layoutMode,
      direction: getLayoutDirection(viewMode),
      nodeWidth: FLOW_NODE_WIDTH,
      nodeHeight: FLOW_NODE_HEIGHT,
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

  const selectGraphNode = useCallback((nodeId: string) => {
    setSelectedNodeId((currentNodeId) => {
      if (currentNodeId !== nodeId) {
        setExpandedNodeIds(new Set())
        setViewMode("explore")
      }
      return nodeId
    })
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
        <StatCard label="当前关系" value={renderRelationships.length} />
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
              {layoutStatus || `${visibleNodes.length} nodes / ${renderRelationships.length} edges`}
            </span>
          </div>
          <ReactFlowProvider>
            <GraphCanvas
              isLoading={isLoading}
              viewMode={viewMode}
              nodes={canvasNodes}
              edges={canvasEdges}
              onSelectNode={selectGraphNode}
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
              related={relationBuckets.related}
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
  viewMode,
  nodes,
  edges,
  onSelectNode,
}: {
  isLoading: boolean
  viewMode: GraphViewMode
  nodes: Node[]
  edges: Edge[]
  onSelectNode: (nodeId: string) => void
}) {
  const updateNodeInternals = useUpdateNodeInternals()
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const resetCountRef = useRef(0)
  const [viewport, setViewport] = useState({ x: 0, y: 0, zoom: 1 })
  const nodeSignature = useMemo(
    () =>
      nodes
        .map((node) => `${node.id}:${Math.round(node.position.x)},${Math.round(node.position.y)}`)
        .sort()
        .join("|"),
    [nodes],
  )
  const edgeSignature = useMemo(() => edges.map((edge) => edge.id).sort().join("|"), [edges])

  const resetViewport = useCallback(() => {
    if (!nodes.length) return
    const nextViewport = getViewportForNodes(nodes, canvasRef.current)
    if (!nextViewport) return
    resetCountRef.current += 1
    setViewport(nextViewport)
    Object.assign(window, {
      __KGTS_GRAPH_RESET_DEBUG__: {
        resetAt: new Date().toISOString(),
        resetCount: resetCountRef.current,
        nodeCount: nodes.length,
        viewport: nextViewport,
      },
    })
  }, [nodes])

  useEffect(() => {
    if (!nodes.length) return
    const measureFrame = window.requestAnimationFrame(() => {
      nodes.forEach((node) => updateNodeInternals(node.id))
      resetViewport()
    })
    return () => {
      window.cancelAnimationFrame(measureFrame)
    }
  }, [nodeSignature, nodes, resetViewport, updateNodeInternals, viewMode])

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
          Object.assign(window, {
            __KGTS_GRAPH_RENDER_DEBUG__: {
              reactFlowNodes: nodes.length,
              reactFlowEdges: edges.length,
              renderedEdgeGroups: document.querySelectorAll(".kg-flow-overlay-edge").length,
              renderedEdgePaths: document.querySelectorAll(".kg-flow-overlay-path").length,
              viewport,
              resetCount: resetCountRef.current,
            },
          })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [edgeSignature, edges.length, nodeSignature, nodes.length, viewport])

  return (
    <div ref={canvasRef} className="relative h-[460px] overflow-hidden bg-slate-50 sm:h-[560px] xl:h-[660px]">
      {isLoading ? (
        <div className="flex h-full items-center justify-center">
          <LoadingSpinner text="加载图谱中..." />
        </div>
      ) : nodes.length === 0 ? (
        <div className="flex h-full items-center justify-center p-8">
          <EmptyState title="暂无图谱节点" description="当前筛选条件下没有可展示的数据。" />
        </div>
      ) : (
        <>
          <ReactFlow
            nodes={nodes}
            edges={[]}
            nodeTypes={graphNodeTypes}
            viewport={viewport}
            onViewportChange={setViewport}
            minZoom={0.08}
            maxZoom={1.8}
            onNodeClick={(_, node) => onSelectNode(node.id)}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
            onError={(code, message) => {
              console.warn("[KGTS graph render]", code, message)
            }}
          >
            <Background color="#cbd5e1" gap={36} />
            <Controls />
            <MiniMap className="hidden sm:block" pannable zoomable nodeColor={(node) => String(node.data?.color || "#64748b")} />
          </ReactFlow>
          <GraphRelationOverlay nodes={nodes} edges={edges} viewport={viewport} />
          <FitViewButton onReset={resetViewport} />
        </>
      )}
    </div>
  )
}

function KnowledgeFlowNode({
  data,
  isConnectable,
  sourcePosition = Position.Right,
  targetPosition = Position.Left,
}: NodeProps<Node<FlowNodeData, "knowledge">>) {
  return (
    <>
      <Handle id="target" className="kg-flow-handle" type="target" position={targetPosition} isConnectable={isConnectable} />
      <span className="kg-flow-label">{data.label}</span>
      <Handle id="source" className="kg-flow-handle" type="source" position={sourcePosition} isConnectable={isConnectable} />
    </>
  )
}

function GraphRelationOverlay({ nodes, edges, viewport }: { nodes: Node[]; edges: Edge[]; viewport: { x: number; y: number; zoom: number } }) {
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])
  const overlayEdges = useMemo(
    () =>
      edges
        .map((edge) => {
          const sourceNode = nodeById.get(edge.source)
          const targetNode = nodeById.get(edge.target)
          if (!sourceNode || !targetNode) return null
          const geometry = getOverlayEdgeGeometry(sourceNode, targetNode)
          if (!geometry) return null
          const isFocused = Boolean(edge.animated || (edge.zIndex && edge.zIndex > 1))
          return {
            ...geometry,
            id: edge.id,
            label: typeof edge.label === "string" ? edge.label : edge.data?.relationType,
            isFocused,
          }
        })
        .filter(Boolean) as Array<{
        id: string
        path: string
        labelX: number
        labelY: number
        sourceX: number
        sourceY: number
        targetX: number
        targetY: number
        sourcePosition: Position
        targetPosition: Position
        label?: string
        isFocused: boolean
      }>,
    [edges, nodeById],
  )

  if (!overlayEdges.length) return null

  return (
    <svg
      className="kg-flow-overlay"
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        overflow: "visible",
        pointerEvents: "none",
        display: "block",
        zIndex: 6,
      }}
    >
      <defs>
        <marker id="kg-flow-arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse">
          <path d="M0,0 L12,6 L0,12 z" fill="#64748b" />
        </marker>
        <marker id="kg-flow-arrow-focus" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse">
          <path d="M0,0 L12,6 L0,12 z" fill="#2563eb" />
        </marker>
      </defs>
      <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.zoom})`}>
        {overlayEdges.map((edge) => {
          const marker = edge.isFocused ? "url(#kg-flow-arrow-focus)" : "url(#kg-flow-arrow)"
          const stroke = edge.isFocused ? "#2563eb" : "#64748b"
          const strokeWidth = edge.isFocused ? 2.8 : 1.8
          const opacity = edge.isFocused ? 1 : 0.7
          return (
            <g key={edge.id} className="kg-flow-overlay-edge">
              <path
                className="kg-flow-overlay-path"
                d={edge.path}
                fill="none"
                stroke={stroke}
                strokeWidth={strokeWidth}
                strokeLinecap="round"
                strokeDasharray={edge.isFocused ? undefined : "5 8"}
                opacity={opacity}
                markerEnd={marker}
              />
              {edge.label ? (
                <g transform={`translate(${edge.labelX}, ${edge.labelY})`}>
                  <rect x={-44} y={-11} width={88} height={22} rx={8} fill="#ffffff" fillOpacity={0.95} stroke={stroke} strokeOpacity={0.25} />
                  <text className="kg-flow-overlay-label" textAnchor="middle" dominantBaseline="middle">
                    {edge.label}
                  </text>
                </g>
              ) : null}
            </g>
          )
        })}
      </g>
    </svg>
  )
}

function FitViewButton({ onReset }: { onReset: () => void }) {
  return (
    <div className="absolute right-3 top-3 z-30">
      <button
        type="button"
        onPointerDown={(event) => {
          event.preventDefault()
          event.stopPropagation()
          onReset()
        }}
        onClick={(event) => {
          event.preventDefault()
          event.stopPropagation()
        }}
        className="nodrag nopan inline-flex items-center gap-2 rounded-lg border bg-white px-2.5 py-2 text-sm shadow-sm hover:bg-slate-50 sm:px-3"
      >
        <RotateCcw size={15} />
        重置视图
      </button>
    </div>
  )
}

function createFlowNode(node: GraphNode, highlightedIds: Set<string>, selectedNodeId: string | null, direction: LayoutDirection): Node {
  const type = node.type || "concept"
  const color = nodeColors[type] || "#0f766e"
  const isSelected = node.id === selectedNodeId
  const isHighlighted = highlightedIds.size === 0 || highlightedIds.has(node.id)
  const { sourcePosition, targetPosition } = getHandlePositions(direction)
  return {
    id: node.id,
    type: "knowledge",
    position: { x: 0, y: 0 },
    sourcePosition,
    targetPosition,
    width: FLOW_NODE_WIDTH,
    height: FLOW_NODE_HEIGHT,
    initialWidth: FLOW_NODE_WIDTH,
    initialHeight: FLOW_NODE_HEIGHT,
    handles: [
      createNodeHandle("target", targetPosition),
      createNodeHandle("source", sourcePosition),
    ],
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

function getOverlayEdgeGeometry(sourceNode: Node, targetNode: Node) {
  const sourceBox = getNodeBox(sourceNode)
  const targetBox = getNodeBox(targetNode)
  const sourceCenter = { x: sourceBox.x + sourceBox.width / 2, y: sourceBox.y + sourceBox.height / 2 }
  const targetCenter = { x: targetBox.x + targetBox.width / 2, y: targetBox.y + targetBox.height / 2 }
  const dx = targetCenter.x - sourceCenter.x
  const dy = targetCenter.y - sourceCenter.y
  const offset = 6

  let sourcePosition: Position
  let targetPosition: Position
  let sourceX: number
  let sourceY: number
  let targetX: number
  let targetY: number

  if (Math.abs(dx) >= Math.abs(dy)) {
    if (dx >= 0) {
      sourcePosition = Position.Right
      targetPosition = Position.Left
      sourceX = sourceBox.x + sourceBox.width + offset
      sourceY = sourceCenter.y
      targetX = targetBox.x - offset
      targetY = targetCenter.y
    } else {
      sourcePosition = Position.Left
      targetPosition = Position.Right
      sourceX = sourceBox.x - offset
      sourceY = sourceCenter.y
      targetX = targetBox.x + targetBox.width + offset
      targetY = targetCenter.y
    }
  } else {
    if (dy >= 0) {
      sourcePosition = Position.Bottom
      targetPosition = Position.Top
      sourceX = sourceCenter.x
      sourceY = sourceBox.y + sourceBox.height + offset
      targetX = targetCenter.x
      targetY = targetBox.y - offset
    } else {
      sourcePosition = Position.Top
      targetPosition = Position.Bottom
      sourceX = sourceCenter.x
      sourceY = sourceBox.y - offset
      targetX = targetCenter.x
      targetY = targetBox.y + targetBox.height + offset
    }
  }

  const [path, labelX, labelY] = getSimpleBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  return {
    path,
    labelX,
    labelY,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  }
}

function getNodeBox(node: Node) {
  const width = getNodeDimension(node.style?.width, typeof node.width === "number" ? node.width : FLOW_NODE_WIDTH)
  const height = getNodeDimension(node.style?.height, typeof node.height === "number" ? node.height : FLOW_NODE_HEIGHT)
  return {
    x: node.position.x,
    y: node.position.y,
    width,
    height,
  }
}

function getViewportForNodes(nodes: Node[], container: HTMLDivElement | null) {
  const width = container?.clientWidth || 960
  const height = container?.clientHeight || 560
  if (!width || !height || !nodes.length) return null

  const bounds = nodes.reduce(
    (acc, node) => {
      const box = getNodeBox(node)
      return {
        minX: Math.min(acc.minX, box.x),
        minY: Math.min(acc.minY, box.y),
        maxX: Math.max(acc.maxX, box.x + box.width),
        maxY: Math.max(acc.maxY, box.y + box.height),
      }
    },
    { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity },
  )

  if (![bounds.minX, bounds.minY, bounds.maxX, bounds.maxY].every(Number.isFinite)) return null

  const graphWidth = Math.max(1, bounds.maxX - bounds.minX)
  const graphHeight = Math.max(1, bounds.maxY - bounds.minY)
  const padding = 56
  const availableWidth = Math.max(1, width - padding * 2)
  const availableHeight = Math.max(1, height - padding * 2)
  const zoom = Math.max(0.08, Math.min(1.25, availableWidth / graphWidth, availableHeight / graphHeight))
  const centerX = bounds.minX + graphWidth / 2
  const centerY = bounds.minY + graphHeight / 2

  return {
    x: width / 2 - centerX * zoom,
    y: height / 2 - centerY * zoom,
    zoom,
  }
}

function createFlowEdges(relations: GraphRelation[], selectedNodeId: string | null): Edge[] {
  const showAllLabels = relations.length <= 90
  return relations
    .filter((relation) => relation.source_id && relation.target_id)
    .map((relation, index) => {
      const isFocused = !!selectedNodeId && (relation.source_id === selectedNodeId || relation.target_id === selectedNodeId)
      const shouldShowLabel = isFocused || showAllLabels
      return {
        id: relation.id || `${relation.source_id}-${relation.relation_type || "related"}-${relation.target_id}-${index}`,
        source: relation.source_id,
        target: relation.target_id,
        label: shouldShowLabel ? relation.relation_type : undefined,
        type: "smoothstep",
        animated: isFocused,
        zIndex: isFocused ? 5 : 0,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: isFocused ? "#2563eb" : "#64748b",
          width: 18,
          height: 18,
        },
        className: isFocused ? "kg-flow-edge kg-flow-edge-focused" : "kg-flow-edge",
        style: {
          stroke: isFocused ? "#2563eb" : "#64748b",
          strokeDasharray: isFocused ? undefined : "5 8",
          strokeLinecap: "round",
          strokeWidth: isFocused ? 2.8 : 1.7,
          opacity: selectedNodeId ? (isFocused ? 0.96 : 0.36) : 0.62,
        },
        labelStyle: { fill: "#1d4ed8", fontSize: 11, fontWeight: 600 },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.94 },
        labelBgPadding: [7, 3] as [number, number],
        labelBgBorderRadius: 6,
      }
    })
}

type LayoutDirection = "RIGHT" | "LEFT" | "DOWN" | "UP"

function getLayoutDirection(viewMode: GraphViewMode): LayoutDirection {
  if (viewMode === "chapterPath") return "DOWN"
  if (viewMode === "prerequisites") return "LEFT"
  return "RIGHT"
}

function getHandlePositions(direction: LayoutDirection) {
  if (direction === "DOWN") return { sourcePosition: Position.Bottom, targetPosition: Position.Top }
  if (direction === "UP") return { sourcePosition: Position.Top, targetPosition: Position.Bottom }
  if (direction === "LEFT") return { sourcePosition: Position.Left, targetPosition: Position.Right }
  return { sourcePosition: Position.Right, targetPosition: Position.Left }
}

function createNodeHandle(type: "source" | "target", position: Position) {
  const half = FLOW_HANDLE_SIZE / 2
  const centerX = FLOW_NODE_WIDTH / 2 - half
  const centerY = FLOW_NODE_HEIGHT / 2 - half
  const coordinates: Record<Position, { x: number; y: number }> = {
    [Position.Left]: { x: -half, y: centerY },
    [Position.Right]: { x: FLOW_NODE_WIDTH - half, y: centerY },
    [Position.Top]: { x: centerX, y: -half },
    [Position.Bottom]: { x: centerX, y: FLOW_NODE_HEIGHT - half },
  }
  return {
    id: type,
    type,
    position,
    ...coordinates[position],
    width: FLOW_HANDLE_SIZE,
    height: FLOW_HANDLE_SIZE,
  }
}

function getNodeDimension(value: unknown, fallback: number): number {
  if (typeof value === "number") return value
  if (typeof value === "string") {
    const parsed = Number.parseFloat(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function hasSameNodeIds(a: Node[], b: Node[]) {
  if (a.length !== b.length) return false
  const ids = new Set(a.map((node) => node.id))
  return b.every((node) => ids.has(node.id))
}

function seedFlowNodes(nextNodes: Node[], currentNodes: Node[]) {
  const currentById = new Map(currentNodes.map((node) => [node.id, node]))
  const columns = Math.max(1, Math.ceil(Math.sqrt(nextNodes.length)))
  return nextNodes.map((node, index) => {
    const current = currentById.get(node.id)
    return {
      ...node,
      position: current?.position || {
        x: (index % columns) * 280,
        y: Math.floor(index / columns) * 120,
      },
    }
  })
}

function mergeRelations(primary: GraphRelation[], secondary: GraphRelation[]) {
  const relations: GraphRelation[] = []
  const seen = new Set<string>()
  primary.concat(secondary).forEach((relation) => {
    const key = relation.id || `${relation.source_id}:${relation.relation_type}:${relation.target_id}`
    if (seen.has(key)) return
    seen.add(key)
    relations.push(relation)
  })
  return relations
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
  related,
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
  related: GraphRelation[]
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

      <section className="rounded-lg border bg-background p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">关系明细</h3>
          <span className="text-xs text-muted-foreground">{related.length} 条</span>
        </div>
        <div className="space-y-3">
          <RelationDetailList title="指向当前节点" selectedNodeId={node.id} relations={incoming.slice(0, 12)} nodeById={nodeById} empty="暂无入边" />
          <RelationDetailList title="从当前节点指出" selectedNodeId={node.id} relations={outgoing.slice(0, 12)} nodeById={nodeById} empty="暂无出边" />
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

function RelationDetailList({
  title,
  selectedNodeId,
  relations,
  nodeById,
  empty,
}: {
  title: string
  selectedNodeId: string
  relations: GraphRelation[]
  nodeById: Map<string, GraphNode>
  empty: string
}) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      {relations.length ? (
        <div className="mt-1 space-y-1.5">
          {relations.map((relation, index) => {
            const otherId = relation.source_id === selectedNodeId ? relation.target_id : relation.source_id
            const otherNode = nodeById.get(otherId)
            const description = relation.description || String(relation.metadata?.description || "")
            return (
              <div key={relation.id || `${relation.source_id}-${relation.target_id}-${index}`} className="rounded-md border bg-muted/30 p-2 text-xs">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary">{relation.relation_type || "related"}</span>
                  <span className="text-foreground">{truncateLabel(otherNode?.label || otherId, 36)}</span>
                </div>
                {description && <div className="mt-1 text-muted-foreground">{truncateLabel(description, 90)}</div>}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="mt-1 text-xs text-muted-foreground">{empty}</div>
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

function getNodeRelations(selectedNodeId: string | null, relations: GraphRelation[], relationType: string) {
  if (!selectedNodeId) return []
  return relations.filter((relation) => {
    if (relationType !== DEFAULT_RELATION && (relation.relation_type || "related") !== relationType) return false
    return relation.source_id === selectedNodeId || relation.target_id === selectedNodeId
  })
}

function getNeighborIds(selectedNodeId: string | null, relations: GraphRelation[]) {
  const ids = new Set<string>()
  if (!selectedNodeId) return ids
  relations.forEach((relation) => {
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

function getRecommendedStarts(nodes: GraphNode[], degreeById: Map<string, number>, contentRelations: GraphRelation[]) {
  const contentDegree = buildDegreeMap(contentRelations)
  return [...nodes]
    .sort((a, b) => getStartNodeScore(b, degreeById, contentDegree) - getStartNodeScore(a, degreeById, contentDegree))
    .slice(0, RECOMMENDED_LIMIT)
}

function buildGraphSubgraph({
  selectedNodeId,
  viewMode,
  expandedNodeIds,
  selectedNeighborIds,
  recommendedNodes,
  baseFilteredNodes,
  rawNodes,
  filteredNodeIds,
  filteredRelations,
  contentRelations,
  nodeById,
  degreeById,
  limit,
}: {
  selectedNodeId: string | null
  viewMode: GraphViewMode
  expandedNodeIds: Set<string>
  selectedNeighborIds: Set<string>
  recommendedNodes: GraphNode[]
  baseFilteredNodes: GraphNode[]
  rawNodes: GraphNode[]
  filteredNodeIds: Set<string>
  filteredRelations: GraphRelation[]
  contentRelations: GraphRelation[]
  nodeById: Map<string, GraphNode>
  degreeById: Map<string, number>
  limit: number
}): GraphSubgraph {
  const anchorNodeId = getAnchorNodeId(selectedNodeId, recommendedNodes, nodeById)

  if (viewMode === "overview") {
    const overviewNodes = getOverviewNodes(baseFilteredNodes, degreeById, filteredRelations, limit)
    const nodeIds = new Set(overviewNodes.map((node) => node.id))
    return finalizeSubgraph({
      nodeIds,
      relations: filteredRelations,
      rawNodes,
      filteredNodeIds,
      anchorNodeId,
      selectedNeighborIds,
      degreeById,
      relationshipLimit: OVERVIEW_EDGE_LIMIT,
      nodeLimit: limit,
    })
  }

  if (!anchorNodeId) {
    const nodeIds = new Set(recommendedNodes.slice(0, RECOMMENDED_LIMIT).map((node) => node.id))
    return finalizeSubgraph({
      nodeIds,
      relations: contentRelations,
      rawNodes,
      filteredNodeIds,
      anchorNodeId,
      selectedNeighborIds,
      degreeById,
      relationshipLimit: FOCUSED_EDGE_LIMIT,
      nodeLimit: Math.min(limit, RECOMMENDED_LIMIT),
    })
  }

  if (viewMode === "chapterPath") {
    return buildPathSubgraph(anchorNodeId, rawNodes, filteredNodeIds, filteredRelations, selectedNeighborIds, degreeById, limit)
  }

  if (viewMode === "prerequisites") {
    return buildPrerequisiteSubgraph(anchorNodeId, rawNodes, filteredNodeIds, filteredRelations, selectedNeighborIds, degreeById, limit)
  }

  if (viewMode === "formulaTheorem") {
    return buildFormulaSubgraph(anchorNodeId, rawNodes, filteredNodeIds, filteredRelations, selectedNeighborIds, degreeById, limit)
  }

  const nodeIds = new Set<string>([anchorNodeId, ...expandedNodeIds, ...selectedNeighborIds])
  getTopRelationsForNode(anchorNodeId, contentRelations, degreeById, 34).forEach((relation) => {
    nodeIds.add(relation.source_id)
    nodeIds.add(relation.target_id)
  })
  recommendedNodes.slice(0, 6).forEach((node) => {
    if (nodeIds.size < limit) nodeIds.add(node.id)
  })
  return finalizeSubgraph({
    nodeIds,
    relations: contentRelations,
    rawNodes,
    filteredNodeIds,
    anchorNodeId,
    selectedNeighborIds,
    degreeById,
    relationshipLimit: FOCUSED_EDGE_LIMIT,
    nodeLimit: limit,
  })
}

function getOverviewNodes(
  nodes: GraphNode[],
  degreeById: Map<string, number>,
  relations: GraphRelation[],
  limit: number,
  requiredIds: Set<string> = new Set(),
) {
  const connectedIds = getRelationNodeIds(relations)
  return [...nodes]
    .sort((a, b) => {
      const requiredDelta = Number(requiredIds.has(b.id)) - Number(requiredIds.has(a.id))
      if (requiredDelta) return requiredDelta
      const connectedDelta = Number(connectedIds.has(b.id)) - Number(connectedIds.has(a.id))
      if (connectedDelta) return connectedDelta
      return getNodeScore(b, degreeById) - getNodeScore(a, degreeById)
    })
    .slice(0, limit)
}

function buildPathSubgraph(
  anchorNodeId: string,
  rawNodes: GraphNode[],
  filteredNodeIds: Set<string>,
  relations: GraphRelation[],
  selectedNeighborIds: Set<string>,
  degreeById: Map<string, number>,
  limit: number,
) {
  const pathRelations = relations.filter((relation) => PATH_RELATION_TYPES.has(relation.relation_type || ""))
  const semanticRelations = relations.filter((relation) => SEMANTIC_RELATION_TYPES.has(relation.relation_type || ""))
  const nodeIds = new Set<string>([anchorNodeId])
  const orderedPath = getOrderedPath(anchorNodeId, pathRelations, 18, 24)
  orderedPath.forEach((id) => nodeIds.add(id))

  getTopRelationsForNode(anchorNodeId, semanticRelations, degreeById, 10).forEach((relation) => {
    if (nodeIds.size < limit) {
      nodeIds.add(relation.source_id)
      nodeIds.add(relation.target_id)
    }
  })

  return finalizeSubgraph({
    nodeIds,
    relations: relations.filter((relation) => PATH_RELATION_TYPES.has(relation.relation_type || "") || relation.source_id === anchorNodeId || relation.target_id === anchorNodeId),
    rawNodes,
    filteredNodeIds,
    anchorNodeId,
    selectedNeighborIds,
    degreeById,
    relationshipLimit: FOCUSED_EDGE_LIMIT,
    nodeLimit: limit,
  })
}

function buildPrerequisiteSubgraph(
  anchorNodeId: string,
  rawNodes: GraphNode[],
  filteredNodeIds: Set<string>,
  relations: GraphRelation[],
  selectedNeighborIds: Set<string>,
  degreeById: Map<string, number>,
  limit: number,
) {
  const prereqRelations = relations.filter((relation) => PREREQUISITE_RELATION_TYPES.has(relation.relation_type || ""))
  const nodeIds = collectDirectedNeighborhood(anchorNodeId, prereqRelations, {
    reverse: true,
    forward: false,
    maxDepth: 3,
    maxNodes: limit,
  })

  if (nodeIds.size < 8) {
    getTopRelationsForNode(anchorNodeId, prereqRelations, degreeById, 22).forEach((relation) => {
      if (nodeIds.size < limit) {
        nodeIds.add(relation.source_id)
        nodeIds.add(relation.target_id)
      }
    })
  }

  return finalizeSubgraph({
    nodeIds,
    relations: prereqRelations,
    rawNodes,
    filteredNodeIds,
    anchorNodeId,
    selectedNeighborIds,
    degreeById,
    relationshipLimit: FOCUSED_EDGE_LIMIT,
    nodeLimit: limit,
  })
}

function buildFormulaSubgraph(
  anchorNodeId: string,
  rawNodes: GraphNode[],
  filteredNodeIds: Set<string>,
  relations: GraphRelation[],
  selectedNeighborIds: Set<string>,
  degreeById: Map<string, number>,
  limit: number,
) {
  const formulaRelations = relations.filter((relation) => FORMULA_RELATION_TYPES.has(relation.relation_type || ""))
  const semanticRelations = relations.filter((relation) => SEMANTIC_RELATION_TYPES.has(relation.relation_type || ""))
  const nodeIds = new Set<string>([anchorNodeId])
  const directFormulaRelations = getTopRelationsForNode(anchorNodeId, formulaRelations, degreeById, 26)
  directFormulaRelations.forEach((relation) => {
    nodeIds.add(relation.source_id)
    nodeIds.add(relation.target_id)
  })

  const formulaIds = new Set(
    Array.from(nodeIds).filter((id) => {
      const type = rawNodes.find((node) => node.id === id)?.type || ""
      return FORMULA_CONTEXT_TYPES.has(type)
    }),
  )

  formulaIds.forEach((formulaId) => {
    getTopRelationsForNode(formulaId, formulaRelations.concat(semanticRelations), degreeById, 8).forEach((relation) => {
      if (nodeIds.size < limit) {
        nodeIds.add(relation.source_id)
        nodeIds.add(relation.target_id)
      }
    })
  })

  if (nodeIds.size < 8) {
    rawNodes
      .filter((node) => FORMULA_CONTEXT_TYPES.has(node.type || "") && filteredNodeIds.has(node.id))
      .sort((a, b) => getNodeScore(b, degreeById) - getNodeScore(a, degreeById))
      .slice(0, 24)
      .forEach((node) => {
        if (nodeIds.size < limit) nodeIds.add(node.id)
      })
  }

  return finalizeSubgraph({
    nodeIds,
    relations: formulaRelations.concat(semanticRelations.filter((relation) => nodeIds.has(relation.source_id) || nodeIds.has(relation.target_id))),
    rawNodes,
    filteredNodeIds,
    anchorNodeId,
    selectedNeighborIds,
    degreeById,
    relationshipLimit: FOCUSED_EDGE_LIMIT,
    nodeLimit: limit,
  })
}

function finalizeSubgraph({
  nodeIds,
  relations,
  rawNodes,
  filteredNodeIds,
  anchorNodeId,
  selectedNeighborIds,
  degreeById,
  relationshipLimit,
  nodeLimit,
}: {
  nodeIds: Set<string>
  relations: GraphRelation[]
  rawNodes: GraphNode[]
  filteredNodeIds: Set<string>
  anchorNodeId: string | null
  selectedNeighborIds: Set<string>
  degreeById: Map<string, number>
  relationshipLimit: number
  nodeLimit: number
}): GraphSubgraph {
  const nodeById = new Map(rawNodes.map((node) => [node.id, node]))
  const keptNodes: GraphNode[] = []
  const seen = new Set<string>()
  const addNode = (nodeId: string) => {
    if (seen.has(nodeId)) return
    const node = nodeById.get(nodeId)
    if (!node) return
    const shouldKeep =
      node.id === anchorNodeId ||
      selectedNeighborIds.has(node.id) ||
      filteredNodeIds.has(node.id) ||
      FORMULA_CONTEXT_TYPES.has(node.type || "")
    if (!shouldKeep) return
    seen.add(node.id)
    keptNodes.push(node)
  }

  if (anchorNodeId) addNode(anchorNodeId)
  Array.from(nodeIds)
    .sort((a, b) => getNodeIdPriority(b, anchorNodeId, selectedNeighborIds, degreeById, nodeById) - getNodeIdPriority(a, anchorNodeId, selectedNeighborIds, degreeById, nodeById))
    .forEach((id) => {
      if (keptNodes.length < nodeLimit) addNode(id)
    })

  const keptNodeIds = new Set(keptNodes.map((node) => node.id))
  const keptRelations = relations
    .filter((relation) => keptNodeIds.has(relation.source_id) && keptNodeIds.has(relation.target_id))
    .sort((a, b) => getRelationPriority(b, anchorNodeId, degreeById) - getRelationPriority(a, anchorNodeId, degreeById))
    .slice(0, relationshipLimit)

  keptRelations.forEach((relation) => {
    addNode(relation.source_id)
    addNode(relation.target_id)
  })

  return {
    nodes: keptNodes
      .sort((a, b) => getVisibleNodePriority(b, anchorNodeId, selectedNeighborIds, degreeById) - getVisibleNodePriority(a, anchorNodeId, selectedNeighborIds, degreeById))
      .slice(0, nodeLimit),
    relationships: keptRelations,
    anchorNodeId,
  }
}

function getAnchorNodeId(selectedNodeId: string | null, recommendedNodes: GraphNode[], nodeById: Map<string, GraphNode>) {
  if (selectedNodeId && nodeById.has(selectedNodeId)) {
    const selectedNode = nodeById.get(selectedNodeId)
    if (!selectedNode || !isStructuralHubNode(selectedNode)) return selectedNodeId
  }
  return recommendedNodes.find((node) => !isStructuralHubNode(node))?.id || recommendedNodes[0]?.id || selectedNodeId
}

function getOrderedPath(anchorNodeId: string, pathRelations: GraphRelation[], beforeLimit: number, afterLimit: number) {
  const incoming = new Map<string, GraphRelation[]>()
  const outgoing = new Map<string, GraphRelation[]>()
  pathRelations.forEach((relation) => {
    if (!incoming.has(relation.target_id)) incoming.set(relation.target_id, [])
    if (!outgoing.has(relation.source_id)) outgoing.set(relation.source_id, [])
    incoming.get(relation.target_id)?.push(relation)
    outgoing.get(relation.source_id)?.push(relation)
  })

  const before: string[] = []
  let current = anchorNodeId
  const seenBefore = new Set([anchorNodeId])
  while (before.length < beforeLimit) {
    const next = (incoming.get(current) || []).find((relation) => !seenBefore.has(relation.source_id))
    if (!next) break
    before.push(next.source_id)
    seenBefore.add(next.source_id)
    current = next.source_id
  }

  const after: string[] = []
  current = anchorNodeId
  const seenAfter = new Set([anchorNodeId])
  while (after.length < afterLimit) {
    const next = (outgoing.get(current) || []).find((relation) => !seenAfter.has(relation.target_id))
    if (!next) break
    after.push(next.target_id)
    seenAfter.add(next.target_id)
    current = next.target_id
  }

  return before.reverse().concat(anchorNodeId, after)
}

function collectDirectedNeighborhood(
  anchorNodeId: string,
  relations: GraphRelation[],
  options: { reverse: boolean; forward: boolean; maxDepth: number; maxNodes: number },
) {
  const incoming = new Map<string, GraphRelation[]>()
  const outgoing = new Map<string, GraphRelation[]>()
  relations.forEach((relation) => {
    if (!incoming.has(relation.target_id)) incoming.set(relation.target_id, [])
    if (!outgoing.has(relation.source_id)) outgoing.set(relation.source_id, [])
    incoming.get(relation.target_id)?.push(relation)
    outgoing.get(relation.source_id)?.push(relation)
  })

  const ids = new Set<string>([anchorNodeId])
  const queue: Array<{ id: string; depth: number }> = [{ id: anchorNodeId, depth: 0 }]
  while (queue.length && ids.size < options.maxNodes) {
    const item = queue.shift()
    if (!item || item.depth >= options.maxDepth) continue
    const nextRelations = [
      ...(options.reverse ? incoming.get(item.id) || [] : []),
      ...(options.forward ? outgoing.get(item.id) || [] : []),
    ]
    nextRelations.forEach((relation) => {
      const nextId = relation.target_id === item.id ? relation.source_id : relation.target_id
      if (ids.has(nextId) || ids.size >= options.maxNodes) return
      ids.add(nextId)
      queue.push({ id: nextId, depth: item.depth + 1 })
    })
  }
  return ids
}

function getTopRelationsForNode(nodeId: string, relations: GraphRelation[], degreeById: Map<string, number>, limit: number) {
  return relations
    .filter((relation) => relation.source_id === nodeId || relation.target_id === nodeId)
    .sort((a, b) => getRelationPriority(b, nodeId, degreeById) - getRelationPriority(a, nodeId, degreeById))
    .slice(0, limit)
}

function getRelationNodeIds(relations: GraphRelation[]) {
  const ids = new Set<string>()
  relations.forEach((relation) => {
    if (relation.source_id) ids.add(relation.source_id)
    if (relation.target_id) ids.add(relation.target_id)
  })
  return ids
}

function getRelationPriority(relation: GraphRelation, selectedNodeId: string | null, degreeById: Map<string, number>) {
  const touchesSelected = selectedNodeId && (relation.source_id === selectedNodeId || relation.target_id === selectedNodeId)
  const typeWeight: Record<string, number> = {
    precedes: 9000,
    references_formula: 8400,
    references_table: 8200,
    derives: 7600,
    defines: 7000,
    explains: 6200,
    depends_on: 5800,
    example_of: 5200,
    supports: 4600,
    causes: 4400,
    contrasts_with: 3600,
    related: 2200,
    contains: 900,
  }
  return (
    (touchesSelected ? 1_000_000 : 0) +
    (typeWeight[relation.relation_type || "related"] || 2400) +
    (degreeById.get(relation.source_id) || 0) * 8 +
    (degreeById.get(relation.target_id) || 0) * 8
  )
}

function getStartNodeScore(node: GraphNode, degreeById: Map<string, number>, contentDegreeById: Map<string, number>) {
  if (isStructuralHubNode(node)) return -1_000_000 + (contentDegreeById.get(node.id) || 0)
  if (!isContentStartNode(node)) return -100_000 + (contentDegreeById.get(node.id) || 0) * 8
  const typeWeight: Record<string, number> = {
    proposition: 900,
    derivation: 850,
    discussion: 760,
    concept: 720,
    formula: 420,
    theorem: 420,
    example: 360,
    note: 120,
    table: 120,
  }
  return (typeWeight[node.type || "concept"] || 520) + (contentDegreeById.get(node.id) || 0) * 32 + (degreeById.get(node.id) || 0) * 2
}

function getNodeScore(node: GraphNode, degreeById: Map<string, number>) {
  const typeWeight: Record<string, number> = {
    proposition: 760,
    derivation: 740,
    concept: 650,
    discussion: 620,
    theorem: 460,
    formula: 440,
    example: 300,
    table: 220,
    note: 200,
    chapter: 80,
  }
  return (typeWeight[node.type || "concept"] || 260) + (degreeById.get(node.id) || 0) * 18
}

function getVisibleNodePriority(node: GraphNode, selectedNodeId: string | null, selectedNeighborIds: Set<string>, degreeById: Map<string, number>) {
  if (selectedNodeId && node.id === selectedNodeId) return 1_000_000
  if (selectedNeighborIds.has(node.id)) return 500_000 + getNodeScore(node, degreeById)
  return getNodeScore(node, degreeById)
}

function getNodeIdPriority(nodeId: string, selectedNodeId: string | null, selectedNeighborIds: Set<string>, degreeById: Map<string, number>, nodeById: Map<string, GraphNode>) {
  const node = nodeById.get(nodeId)
  if (!node) return 0
  return getVisibleNodePriority(node, selectedNodeId, selectedNeighborIds, degreeById)
}

function isStructuralHubNode(node: GraphNode) {
  return (node.type || "") === "chapter"
}

function isContentStartNode(node: GraphNode) {
  return CONTENT_START_TYPES.has(node.type || "concept")
}

function isStructuralRelation(relation: GraphRelation) {
  return STRUCTURAL_RELATION_TYPES.has(relation.relation_type || "")
}

function buildDegreeMap(relations: GraphRelation[]) {
  const map = new Map<string, number>()
  relations.forEach((relation) => {
    map.set(relation.source_id, (map.get(relation.source_id) || 0) + 1)
    map.set(relation.target_id, (map.get(relation.target_id) || 0) + 1)
  })
  return map
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
