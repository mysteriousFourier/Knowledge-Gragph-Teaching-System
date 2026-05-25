import { createFileRoute, Link } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, ReactFlowProvider, type Edge, type Node, type NodeProps, useUpdateNodeInternals } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import {
  BookOpen,
  ClipboardList,
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
  nodeType: string
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
  { id: "elk", label: "ELK 自动定位" },
  { id: "dagre", label: "Dagre 快速定位" },
  { id: "grid", label: "网格定位" },
]

const layoutDescriptions: Record<GraphLayoutMode, string> = {
  elk: "ELK 分层定位会优先按关系方向排列节点；失败时自动回退到 Dagre，再回退到网格。",
  dagre: "Dagre 快速定位适合中等规模有向关系；失败时自动回退到网格。",
  grid: "网格定位不依赖关系结构，适合作为大图或异常数据的稳定兜底。",
}

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
const CANVAS_EDGE_LIMITS: Record<GraphViewMode, number> = {
  explore: 18,
  formulaTheorem: 36,
  prerequisites: 36,
  chapterPath: 100,
  overview: 140,
}
const CANVAS_CONTEXT_EDGE_LIMITS: Record<GraphViewMode, number> = {
  explore: 0,
  formulaTheorem: 12,
  prerequisites: 12,
  chapterPath: 100,
  overview: 140,
}
const CANVAS_LABEL_LIMIT = 6
const FORMULA_CANVAS_NODE_LIMIT = 56
const EDGE_ROUTE_OBSTACLE_PADDING = 16
const EDGE_ROUTE_LANE_GAP = 34
const EDGE_ROUTE_CORRIDOR_PADDING = 360
const EDGE_ROUTE_OBSTACLE_LIMIT = 64
const EDGE_PORT_SPACING = 18
const LIMITED_NODE_FETCH_LIMIT = 5000
const LIMITED_RELATION_FETCH_LIMIT = 50000
const ALL_NODE_FETCH_LIMIT = 10000
const ALL_RELATION_FETCH_LIMIT = 50000
const STRUCTURAL_RELATION_TYPES = new Set(["contains"])
const PATH_RELATION_TYPES = new Set(["precedes"])
const FORMULA_RELATION_TYPES = new Set(["references_formula", "references_table", "references_figure", "references_example"])
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
  "references_figure",
  "references_example",
])
const FORMULA_CONTEXT_TYPES = new Set(["formula", "theorem", "table", "note"])
const CONTENT_START_TYPES = new Set(["proposition", "derivation", "discussion", "concept"])
const CHAPTER_PATH_INTERNAL_TYPES = new Set(["section", "proposition", "derivation", "discussion", "concept", "table", "figure", "example", "formula", "theorem", "note", "observation"])

function GraphPage() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canEditGraph = user?.role === "teacher"
  const [searchTerm, setSearchTerm] = useState("")
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [graphFocusNodeId, setGraphFocusNodeId] = useState<string | null>(null)
  const [nodeType, setNodeType] = useState(DEFAULT_TYPE)
  const [relationType, setRelationType] = useState(DEFAULT_RELATION)
  const [viewMode, setViewMode] = useState<GraphViewMode>("explore")
  const [layoutMode, setLayoutMode] = useState<GraphLayoutMode>("elk")
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set())
  const [flowNodes, setFlowNodes] = useState<Node[]>([])
  const [layoutReadySignature, setLayoutReadySignature] = useState("")
  const [layoutStatus, setLayoutStatus] = useState("")
  const [editMessage, setEditMessage] = useState("")

  const showAllNodes = viewMode === "overview" || viewMode === "chapterPath"
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
  const graphRelationships = useMemo(() => relationshipsData?.relationships || [], [relationshipsData?.relationships])
  const stats = statsData?.data
  const nodeById = useMemo(() => new Map(rawNodes.map((node) => [node.id, node])), [rawNodes])
  const degreeById = useMemo(() => buildDegreeMap(rawRelationships), [rawRelationships])
  const graphDegreeById = useMemo(() => buildDegreeMap(graphRelationships), [graphRelationships])

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
  const graphContentRelations = useMemo(
    () =>
      graphRelationships.filter((relation) => {
        if (isStructuralRelation(relation)) return false
        return nodeById.has(relation.source_id) && nodeById.has(relation.target_id)
      }),
    [graphRelationships, nodeById],
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
  const graphFocusRelationships = useMemo(
    () => getNodeRelations(graphFocusNodeId, graphRelationships, relationType),
    [graphFocusNodeId, graphRelationships, relationType],
  )
  const graphNeighborIds = useMemo(() => getNeighborIds(graphFocusNodeId, graphFocusRelationships), [graphFocusNodeId, graphFocusRelationships])
  const recommendedNodes = useMemo(() => getRecommendedStarts(baseFilteredNodes, graphDegreeById, graphContentRelations), [baseFilteredNodes, graphContentRelations, graphDegreeById])
  const orderedChapterNodes = useMemo(() => getOrderedChapterNodes(rawNodes, filteredNodeIds), [filteredNodeIds, rawNodes])
  const formulaStartNodeId = useMemo(
    () =>
      baseFilteredNodes
        .filter((node) => FORMULA_CONTEXT_TYPES.has(node.type || ""))
        .sort((a, b) => getNodeScore(b, graphDegreeById) - getNodeScore(a, graphDegreeById))[0]?.id || null,
    [baseFilteredNodes, graphDegreeById],
  )

  useEffect(() => {
    const recommendedStart = recommendedNodes[0]?.id
    if (!recommendedStart) return
    if (!selectedNodeId) {
      setSelectedNodeId(recommendedStart)
    }
    if (!graphFocusNodeId) {
      setGraphFocusNodeId(recommendedStart)
    }
  }, [graphFocusNodeId, recommendedNodes, selectedNodeId])

  const graphSubgraph = useMemo<GraphSubgraph>(() => {
    const filteredRelations = graphRelationships.filter((relation) => {
      if (relationType !== DEFAULT_RELATION && (relation.relation_type || "related") !== relationType) return false
      return nodeById.has(relation.source_id) && nodeById.has(relation.target_id)
    })

    return buildGraphSubgraph({
      viewMode,
      selectedNodeId: graphFocusNodeId,
      expandedNodeIds,
      selectedNeighborIds: graphNeighborIds,
      recommendedNodes,
      baseFilteredNodes,
      rawNodes,
      filteredNodeIds,
      filteredRelations,
      contentRelations: graphContentRelations,
      nodeById,
      degreeById: graphDegreeById,
      limit: viewMode === "overview" ? OVERVIEW_LIMIT : FOCUSED_LIMIT,
    })
  }, [
    baseFilteredNodes,
    expandedNodeIds,
    filteredNodeIds,
    graphContentRelations,
    graphDegreeById,
    graphFocusNodeId,
    graphNeighborIds,
    graphRelationships,
    nodeById,
    rawNodes,
    recommendedNodes,
    relationType,
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
    if (viewMode === "formulaTheorem") {
      return new Set([
        selectedNodeId,
        ...(graphFocusNodeId ? [graphFocusNodeId] : []),
        ...selectedNeighborIds,
        ...graphNeighborIds,
        ...visibleNodes.filter((node) => FORMULA_CONTEXT_TYPES.has(node.type || "")).map((node) => node.id),
      ])
    }
    if (viewMode === "chapterPath") {
      return new Set(visibleNodes.map((node) => node.id))
    }
    return new Set([selectedNodeId, ...(graphFocusNodeId ? [graphFocusNodeId] : []), ...(viewMode === "explore" ? graphNeighborIds : [])])
  }, [graphFocusNodeId, graphNeighborIds, selectedNeighborIds, selectedNodeId, viewMode, visibleNodes])

  const baseFlowNodes = useMemo<Node[]>(
    () => visibleNodes.map((node) => createFlowNode(node, highlightedIds, selectedNodeId, getLayoutDirection(viewMode))),
    [highlightedIds, selectedNodeId, viewMode, visibleNodes],
  )
  const canvasRelationships = useMemo(
    () => selectCanvasRelationships(renderRelationships, graphFocusNodeId, viewMode, graphDegreeById),
    [graphDegreeById, graphFocusNodeId, renderRelationships, viewMode],
  )
  const canvasRelationshipNodeIds = useMemo(() => getRelationNodeIds(canvasRelationships), [canvasRelationships])
  const flowEdges = useMemo<Edge[]>(
    () => createFlowEdges(canvasRelationships, selectedNodeId),
    [canvasRelationships, selectedNodeId],
  )
  const canvasBaseFlowNodes = useMemo(
    () => selectCanvasNodes(baseFlowNodes, canvasRelationshipNodeIds, graphFocusNodeId, viewMode),
    [baseFlowNodes, canvasRelationshipNodeIds, graphFocusNodeId, viewMode],
  )
  const baseFlowNodeIds = useMemo(() => new Set(canvasBaseFlowNodes.map((node) => node.id)), [canvasBaseFlowNodes])
  const layoutEdges = useMemo<Edge[]>(
    () => flowEdges.filter((edge) => baseFlowNodeIds.has(edge.source) && baseFlowNodeIds.has(edge.target)),
    [baseFlowNodeIds, flowEdges],
  )
  const effectiveLayoutMode: GraphLayoutMode = viewMode === "formulaTheorem" ? "grid" : layoutMode
  const effectiveLayoutEdges = layoutEdges
  const layoutSignature = useMemo(
    () => getLayoutSignature(canvasBaseFlowNodes, effectiveLayoutEdges, graphFocusNodeId, viewMode, effectiveLayoutMode),
    [canvasBaseFlowNodes, effectiveLayoutEdges, effectiveLayoutMode, graphFocusNodeId, viewMode],
  )
  const canvasNodes = useMemo<Node[]>(() => seedFlowNodes(canvasBaseFlowNodes, flowNodes), [canvasBaseFlowNodes, flowNodes])
  const canvasNodeIds = useMemo(() => new Set(canvasNodes.map((node) => node.id)), [canvasNodes])
  const canvasEdges = useMemo<Edge[]>(
    () => flowEdges.filter((edge) => canvasNodeIds.has(edge.source) && canvasNodeIds.has(edge.target)),
    [canvasNodeIds, flowEdges],
  )
  const isLayoutReady = layoutReadySignature === layoutSignature
  const renderedCanvasEdges = useMemo(() => (isLayoutReady ? canvasEdges : []), [canvasEdges, isLayoutReady])
  const hiddenCanvasEdgeCount = flowEdges.length - canvasEdges.length

  useEffect(() => {
    Object.assign(window, {
      __KGTS_GRAPH_DEBUG__: {
        selectedNodeId,
        graphFocusNodeId,
        anchorNodeId: graphSubgraph.anchorNodeId,
        viewMode,
        rawRelationshipPayload: relationshipsData?.rawCount ?? rawRelationships.length,
        missingEndpointRelationships: relationshipsData?.missingEndpointCount ?? 0,
        missingNodeRelationships: relationshipsData?.missingNodeCount ?? 0,
        rawNodes: rawNodes.length,
        rawRelationships: rawRelationships.length,
        contentRelationships: graphContentRelations.length,
        visibleNodes: visibleNodes.length,
        visibleRelationships: visibleRelationships.length,
        renderRelationships: renderRelationships.length,
        canvasRelationships: canvasRelationships.length,
        canvasRelationshipNodes: canvasRelationshipNodeIds.size,
        flowNodes: flowNodes.length,
        flowEdges: flowEdges.length,
        layoutEdges: layoutEdges.length,
        canvasNodes: canvasNodes.length,
        canvasEdges: canvasEdges.length,
        renderedCanvasEdges: renderedCanvasEdges.length,
        isLayoutReady,
        hiddenCanvasEdges: hiddenCanvasEdgeCount,
        selectedRelations: focusedRelationships.length,
        selectedNeighbors: selectedNeighborIds.size,
        graphNeighbors: graphNeighborIds.size,
      },
    })
  }, [
    canvasEdges.length,
    canvasRelationships.length,
    canvasRelationshipNodeIds.size,
    canvasNodes.length,
    graphContentRelations.length,
    flowEdges.length,
    flowNodes.length,
    focusedRelationships.length,
    graphFocusNodeId,
    graphSubgraph.anchorNodeId,
    graphNeighborIds.size,
    hiddenCanvasEdgeCount,
    layoutEdges.length,
    isLayoutReady,
    rawNodes.length,
    rawRelationships.length,
    renderedCanvasEdges.length,
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
    const currentLayoutSignature = layoutSignature
    setLayoutReadySignature("")
    setFlowNodes((currentNodes) => seedFlowNodes(canvasBaseFlowNodes, currentNodes))
    setLayoutStatus(
      viewMode === "formulaTheorem"
        ? "正在恢复公式节点阵列..."
        : layoutMode === "elk"
          ? "正在计算 ELK 自动定位..."
          : layoutMode === "dagre"
            ? "正在计算 Dagre 快速定位..."
            : "正在计算网格定位...",
    )
    const layoutPromise =
      viewMode === "formulaTheorem"
        ? Promise.resolve(layoutFormulaGridNodes(canvasBaseFlowNodes, graphFocusNodeId, effectiveLayoutEdges))
        : layoutGraphNodes(canvasBaseFlowNodes, effectiveLayoutEdges, {
            mode: effectiveLayoutMode,
            direction: getLayoutDirection(viewMode),
            nodeWidth: FLOW_NODE_WIDTH,
            nodeHeight: FLOW_NODE_HEIGHT,
          })
    layoutPromise.then((nodes) => {
      if (cancelled) return
      setFlowNodes(nodes)
      setLayoutReadySignature(currentLayoutSignature)
      setLayoutStatus("")
    })
    return () => {
      cancelled = true
    }
  }, [layoutSignature])

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
    setGraphFocusNodeId(nodeId)
    setViewMode("explore")
    setExpandedNodeIds(new Set())
    setEditMessage("")
  }, [])

  const selectGraphNode = useCallback((nodeId: string) => {
    const node = nodeById.get(nodeId)
    setSelectedNodeId(nodeId)
    setEditMessage("")
    if (viewMode === "chapterPath") {
      if (isStructuralHubNode(node)) {
        setGraphFocusNodeId(nodeId)
        setExpandedNodeIds(new Set([nodeId]))
        return
      }
      const chapterId = findContainingChapterId(nodeId, graphRelationships, nodeById) || (isStructuralHubNode(nodeById.get(graphFocusNodeId || "")) ? graphFocusNodeId : null)
      if (chapterId) {
        setGraphFocusNodeId(chapterId)
        setExpandedNodeIds(new Set([chapterId]))
        return
      }
    }
    setGraphFocusNodeId(nodeId)
    setExpandedNodeIds(new Set())
  }, [graphFocusNodeId, graphRelationships, nodeById, viewMode])

  const resetGraphView = useCallback(() => {
    const startNodeId =
      viewMode === "formulaTheorem"
        ? formulaStartNodeId || recommendedNodes[0]?.id || null
        : viewMode === "chapterPath"
          ? orderedChapterNodes[0]?.id || recommendedNodes[0]?.id || null
          : recommendedNodes[0]?.id || null
    setSelectedNodeId(startNodeId)
    setGraphFocusNodeId(startNodeId)
    setExpandedNodeIds(new Set())
    setEditMessage("")
    return startNodeId
  }, [formulaStartNodeId, orderedChapterNodes, recommendedNodes, viewMode])

  const selectViewMode = useCallback(
    (mode: GraphViewMode) => {
      setViewMode(mode)
      setExpandedNodeIds(new Set())
      setEditMessage("")
      if (mode === "formulaTheorem") {
        const startNodeId = formulaStartNodeId || recommendedNodes[0]?.id || null
        setSelectedNodeId(startNodeId)
        setGraphFocusNodeId(startNodeId)
      } else if (mode === "chapterPath") {
        const startNodeId = orderedChapterNodes[0]?.id || recommendedNodes[0]?.id || null
        setSelectedNodeId(startNodeId)
        setGraphFocusNodeId(startNodeId)
      }
    },
    [formulaStartNodeId, orderedChapterNodes, recommendedNodes],
  )

  const expandSelected = useCallback(() => {
    if (!selectedNodeId) return
    if (viewMode === "chapterPath" && isStructuralHubNode(nodeById.get(selectedNodeId))) {
      setGraphFocusNodeId(selectedNodeId)
      setExpandedNodeIds(new Set([selectedNodeId]))
      return
    }
    setGraphFocusNodeId(selectedNodeId)
    setExpandedNodeIds((prev) => new Set([...prev, selectedNodeId, ...selectedNeighborIds]))
  }, [nodeById, selectedNeighborIds, selectedNodeId, viewMode])

  const resetToFocus = useCallback(() => {
    if (viewMode === "chapterPath") {
      const startNodeId = orderedChapterNodes[0]?.id || selectedNodeId
      setSelectedNodeId(startNodeId)
      setGraphFocusNodeId(startNodeId)
      setExpandedNodeIds(new Set())
      return
    }
    setGraphFocusNodeId(selectedNodeId)
    setExpandedNodeIds(new Set())
    setViewMode("explore")
  }, [orderedChapterNodes, selectedNodeId, viewMode])

  const backToStarts = useCallback(() => {
    const startNodeId = viewMode === "chapterPath" ? orderedChapterNodes[0]?.id || null : recommendedNodes[0]?.id || null
    setSelectedNodeId(startNodeId)
    setGraphFocusNodeId(startNodeId)
    setExpandedNodeIds(new Set())
    if (viewMode !== "chapterPath") {
      setViewMode("explore")
    }
  }, [orderedChapterNodes, recommendedNodes, viewMode])

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
            <button key={mode.id} type="button" onClick={() => selectViewMode(mode.id)} className={cnSegment(viewMode === mode.id)}>
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
            {viewMode === "chapterPath" ? "展开章节" : "展开邻居"}
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
          <span className="text-sm text-muted-foreground">{layoutDescriptions[layoutMode]}</span>
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
              {layoutStatus || `${visibleNodes.length} nodes / ${canvasRelationships.length} of ${renderRelationships.length} edges`}
            </span>
          </div>
          <ReactFlowProvider>
            <GraphCanvas
              isLoading={isLoading}
              isLayoutReady={isLayoutReady}
              viewMode={viewMode}
              focusNodeId={graphFocusNodeId}
              nodes={canvasNodes}
              edges={renderedCanvasEdges}
              graphSignature={layoutSignature}
              onSelectNode={selectGraphNode}
              onResetGraphView={resetGraphView}
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
              onPrepare={() => {
                window.location.href = `/teacher/prepare?nodeId=${encodeURIComponent(selectedNode.id)}`
              }}
              onSelectNode={selectGraphNode}
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
  isLayoutReady,
  viewMode,
  focusNodeId,
  nodes,
  edges,
  graphSignature,
  onSelectNode,
  onResetGraphView,
}: {
  isLoading: boolean
  isLayoutReady: boolean
  viewMode: GraphViewMode
  focusNodeId: string | null
  nodes: Node[]
  edges: Edge[]
  graphSignature: string
  onSelectNode: (nodeId: string) => void
  onResetGraphView: () => string | null
}) {
  const updateNodeInternals = useUpdateNodeInternals()
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const resetCountRef = useRef(0)
  const fittedGraphSignatureRef = useRef("")
  const pinnedClickRef = useRef<{ nodeId: string; screenX: number; screenY: number; graphSignature: string } | null>(null)
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

  const fitViewport = useCallback(() => {
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

  const centerViewportOnNode = useCallback(
    (nodeId: string | null, preferredZoom = 1) => {
      if (!nodeId) return false
      const node = nodes.find((item) => item.id === nodeId)
      const nextViewport = getViewportForNode(node, canvasRef.current, preferredZoom)
      if (!nextViewport) return false
      resetCountRef.current += 1
      setViewport(nextViewport)
      Object.assign(window, {
        __KGTS_GRAPH_RESET_DEBUG__: {
          resetAt: new Date().toISOString(),
          resetCount: resetCountRef.current,
          resetKind: "focus-node",
          focusNodeId: nodeId,
          nodeCount: nodes.length,
          viewport: nextViewport,
        },
      })
      return true
    },
    [nodes],
  )

  const resetViewport = useCallback(() => {
    pinnedClickRef.current = null
    const resetFocusNodeId = onResetGraphView()
    window.requestAnimationFrame(() => {
      if (viewMode === "formulaTheorem" && centerViewportOnNode(resetFocusNodeId, Math.max(viewport.zoom || 1, 0.9))) return
      fitViewport()
    })
  }, [centerViewportOnNode, fitViewport, onResetGraphView, viewMode, viewport.zoom])

  const selectNodeWithoutJump = useCallback(
    (nodeId: string) => {
      if (viewMode === "formulaTheorem") {
        pinnedClickRef.current = null
        onSelectNode(nodeId)
        window.requestAnimationFrame(() => centerViewportOnNode(nodeId, Math.max(viewport.zoom || 1, 0.9)))
        return
      }
      const node = nodes.find((item) => item.id === nodeId)
      if (node) {
        const box = getNodeBox(node)
        pinnedClickRef.current = {
          nodeId,
          screenX: (box.x + box.width / 2) * viewport.zoom + viewport.x,
          screenY: (box.y + box.height / 2) * viewport.zoom + viewport.y,
          graphSignature,
        }
      }
      onSelectNode(nodeId)
    },
    [centerViewportOnNode, graphSignature, nodes, onSelectNode, viewMode, viewport],
  )

  useEffect(() => {
    if (!nodes.length || !isLayoutReady) return
    const measureFrame = window.requestAnimationFrame(() => {
      nodes.forEach((node) => updateNodeInternals(node.id))
      if (fittedGraphSignatureRef.current !== graphSignature) {
        fittedGraphSignatureRef.current = graphSignature
        if (viewMode === "formulaTheorem" && centerViewportOnNode(focusNodeId, Math.max(viewport.zoom || 1, 0.9))) {
          pinnedClickRef.current = null
          return
        }
        const pinnedClick = pinnedClickRef.current
        const pinnedNode = pinnedClick?.graphSignature !== graphSignature ? nodes.find((node) => node.id === pinnedClick?.nodeId) : null
        if (pinnedClick && pinnedNode) {
          const pinnedBox = getNodeBox(pinnedNode)
          setViewport((currentViewport) => ({
            ...currentViewport,
            x: pinnedClick.screenX - (pinnedBox.x + pinnedBox.width / 2) * currentViewport.zoom,
            y: pinnedClick.screenY - (pinnedBox.y + pinnedBox.height / 2) * currentViewport.zoom,
          }))
          pinnedClickRef.current = null
        } else {
          fitViewport()
        }
      }
    })
    return () => {
      window.cancelAnimationFrame(measureFrame)
    }
  }, [centerViewportOnNode, fitViewport, focusNodeId, graphSignature, isLayoutReady, nodeSignature, nodes, updateNodeInternals, viewMode, viewport.zoom])

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
          Object.assign(window, {
            __KGTS_GRAPH_RENDER_DEBUG__: {
              reactFlowNodes: nodes.length,
              reactFlowEdges: edges.length,
              renderedNativeEdges: document.querySelectorAll(".react-flow__edge").length,
              renderedEdgeGroups: document.querySelectorAll(".kg-flow-overlay-edge").length,
              renderedEdgePaths: document.querySelectorAll(".kg-flow-overlay-path").length,
              graphSignature,
              viewport,
              resetCount: resetCountRef.current,
            },
          })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [edgeSignature, edges.length, graphSignature, nodeSignature, nodes.length, viewport])

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
            onNodeClick={(_, node) => selectNodeWithoutJump(node.id)}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
            onError={(code, message) => {
              console.warn("[KGTS graph render]", code, message)
            }}
          >
            <Background color="#cbd5e1" gap={36} />
            <GraphRelationOverlay key={graphSignature} nodes={nodes} edges={edges} viewport={viewport} />
            <Controls />
            <MiniMap className="hidden sm:block" pannable zoomable nodeColor={(node) => String(node.data?.color || "#64748b")} />
          </ReactFlow>
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
  const edgeOffsets = useMemo(() => getEdgePortOffsets(edges), [edges])
  const overlayEdges = useMemo(
    () =>
      edges
        .map((edge) => {
          const sourceNode = nodeById.get(edge.source)
          const targetNode = nodeById.get(edge.target)
          if (!sourceNode || !targetNode || sourceNode.id === targetNode.id) return null
          const geometry = getOverlayEdgeGeometry(sourceNode, targetNode, nodes, edgeOffsets.get(edge.id) || 0)
          if (!geometry) return null
          const isFocused = Boolean(edge.animated || (edge.zIndex && edge.zIndex > 0))
          return {
            ...geometry,
            id: edge.id,
            label: typeof edge.label === "string" ? edge.label : undefined,
            isFocused,
          }
        })
        .filter(Boolean) as Array<{
        id: string
        path: string
        labelX: number
        labelY: number
        label?: string
        isFocused: boolean
      }>,
    [edgeOffsets, edges, nodeById, nodes],
  )

  if (!overlayEdges.length) return null

  return (
    <svg className="kg-flow-overlay" aria-hidden="true">
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
          const strokeWidth = edge.isFocused ? 2.6 : 1.7
          const opacity = edge.isFocused ? 0.98 : 0.58
          return (
            <path
              key={`${edge.id}-path`}
              className="kg-flow-overlay-path"
              d={edge.path}
              fill="none"
              stroke={stroke}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={edge.isFocused ? undefined : "5 8"}
              opacity={opacity}
              markerEnd={marker}
            />
          )
        })}
        {overlayEdges.map((edge) => {
          const stroke = edge.isFocused ? "#2563eb" : "#64748b"
          const labelText = edge.label ? truncateRelationLabel(edge.label) : ""
          const labelWidth = Math.min(148, Math.max(56, labelText.length * 7 + 22))
          if (!labelText) return null
          return (
            <g key={`${edge.id}-label`} className="kg-flow-overlay-edge" transform={`translate(${edge.labelX}, ${edge.labelY})`}>
              <rect x={-labelWidth / 2} y={-10} width={labelWidth} height={20} rx={6} fill="#ffffff" fillOpacity={0.98} stroke={stroke} strokeOpacity={0.32} />
              <text className="kg-flow-overlay-label" textAnchor="middle" dominantBaseline="middle">
                {labelText}
              </text>
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
      nodeType: type,
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

function getOverlayEdgeGeometry(sourceNode: Node, targetNode: Node, allNodes: Node[], edgeOffset: number) {
  const sourceBox = getNodeBox(sourceNode)
  const targetBox = getNodeBox(targetNode)
  const sourceCenter = { x: sourceBox.x + sourceBox.width / 2, y: sourceBox.y + sourceBox.height / 2 }
  const targetCenter = { x: targetBox.x + targetBox.width / 2, y: targetBox.y + targetBox.height / 2 }
  const dx = targetCenter.x - sourceCenter.x
  const dy = targetCenter.y - sourceCenter.y
  const sourceSide = getEdgeSide(dx, dy, "source")
  const targetSide = getEdgeSide(dx, dy, "target")
  const source = getBoxPort(sourceBox, sourceSide, edgeOffset)
  const target = getBoxPort(targetBox, targetSide, -edgeOffset)

  const obstacleBoxes = getRouteObstacles(sourceNode, targetNode, allNodes)
  const points = routeOrthogonalPath(source, target, sourceSide, targetSide, obstacleBoxes)
  const path = pointsToPath(points)
  const labelPoint = getPathLabelPoint(points)

  return {
    path,
    labelX: labelPoint.x,
    labelY: labelPoint.y,
  }
}

function getEdgeSide(dx: number, dy: number, endpoint: "source" | "target"): EdgeSide {
  const forward = endpoint === "source" ? 1 : -1
  if (Math.abs(dx) >= Math.abs(dy)) return dx * forward >= 0 ? "right" : "left"
  return dy * forward >= 0 ? "bottom" : "top"
}

function getBoxPort(box: NodeBox, side: EdgeSide, offset = 0): Point {
  const centerX = box.x + box.width / 2
  const centerY = box.y + box.height / 2
  if (side === "left") return { x: box.x - 2, y: clamp(centerY + offset, box.y + 14, box.y + box.height - 14) }
  if (side === "right") return { x: box.x + box.width + 2, y: clamp(centerY + offset, box.y + 14, box.y + box.height - 14) }
  if (side === "top") return { x: clamp(centerX + offset, box.x + 18, box.x + box.width - 18), y: box.y - 2 }
  return { x: clamp(centerX + offset, box.x + 18, box.x + box.width - 18), y: box.y + box.height + 2 }
}

function getRouteObstacles(sourceNode: Node, targetNode: Node, allNodes: Node[]) {
  const sourceBox = getNodeBox(sourceNode)
  const targetBox = getNodeBox(targetNode)
  const corridor = getCorridorBox(sourceBox, targetBox, EDGE_ROUTE_CORRIDOR_PADDING)
  return allNodes
    .filter((node) => node.id !== sourceNode.id && node.id !== targetNode.id)
    .map((node) => inflateBox(getNodeBox(node), EDGE_ROUTE_OBSTACLE_PADDING))
    .filter((box) => boxesOverlap(box, corridor))
    .sort((a, b) => boxDistanceToPoint(a, sourceBox) - boxDistanceToPoint(b, sourceBox))
    .slice(0, EDGE_ROUTE_OBSTACLE_LIMIT)
}

function routeOrthogonalPath(source: Point, target: Point, sourceSide: EdgeSide, targetSide: EdgeSide, obstacles: NodeBox[]) {
  const sourceLead = getLeadPoint(source, sourceSide, EDGE_ROUTE_LANE_GAP)
  const targetLead = getLeadPoint(target, targetSide, EDGE_ROUTE_LANE_GAP)
  const xLanes = getRouteLanes(sourceLead.x, targetLead.x, obstacles, "x")
  const yLanes = getRouteLanes(sourceLead.y, targetLead.y, obstacles, "y")
  const candidates: Point[][] = []

  xLanes.forEach((x) => {
    candidates.push([source, sourceLead, { x, y: sourceLead.y }, { x, y: targetLead.y }, targetLead, target])
  })
  yLanes.forEach((y) => {
    candidates.push([source, sourceLead, { x: sourceLead.x, y }, { x: targetLead.x, y }, targetLead, target])
  })
  xLanes.forEach((x) => {
    yLanes.forEach((y) => {
      candidates.push([source, sourceLead, { x, y: sourceLead.y }, { x, y }, { x: targetLead.x, y }, targetLead, target])
      candidates.push([source, sourceLead, { x: sourceLead.x, y }, { x, y }, { x, y: targetLead.y }, targetLead, target])
    })
  })

  return candidates
    .map(compactPathPoints)
    .sort((a, b) => scoreOrthogonalPath(a, obstacles) - scoreOrthogonalPath(b, obstacles))[0]
}

type Point = { x: number; y: number }
type NodeBox = { x: number; y: number; width: number; height: number }
type EdgeSide = "left" | "right" | "top" | "bottom"

function getEdgePortOffsets(edges: Edge[]) {
  const edgeIdsByNode = new Map<string, string[]>()
  edges.forEach((edge) => {
    if (!edgeIdsByNode.has(edge.source)) edgeIdsByNode.set(edge.source, [])
    if (!edgeIdsByNode.has(edge.target)) edgeIdsByNode.set(edge.target, [])
    edgeIdsByNode.get(edge.source)?.push(edge.id)
    edgeIdsByNode.get(edge.target)?.push(edge.id)
  })

  const offsets = new Map<string, number[]>()
  edgeIdsByNode.forEach((edgeIds) => {
    const orderedIds = [...edgeIds].sort()
    const center = (orderedIds.length - 1) / 2
    orderedIds.forEach((edgeId, index) => {
      const current = offsets.get(edgeId) || []
      current.push((index - center) * EDGE_PORT_SPACING)
      offsets.set(edgeId, current)
    })
  })

  return new Map(Array.from(offsets, ([edgeId, values]) => [edgeId, average(values)]))
}

function getLeadPoint(point: Point, side: EdgeSide, gap: number): Point {
  if (side === "left") return { x: point.x - gap, y: point.y }
  if (side === "right") return { x: point.x + gap, y: point.y }
  if (side === "top") return { x: point.x, y: point.y - gap }
  return { x: point.x, y: point.y + gap }
}

function getRouteLanes(sourceValue: number, targetValue: number, obstacles: NodeBox[], axis: "x" | "y") {
  const min = Math.min(sourceValue, targetValue)
  const max = Math.max(sourceValue, targetValue)
  const midpoint = (sourceValue + targetValue) / 2
  const values = new Set<number>([sourceValue, targetValue, midpoint])
  const outsideGap = EDGE_ROUTE_LANE_GAP * 1.7

  values.add(min - outsideGap)
  values.add(max + outsideGap)
  obstacles.forEach((box) => {
    const start = axis === "x" ? box.x : box.y
    const end = axis === "x" ? box.x + box.width : box.y + box.height
    values.add(start - EDGE_ROUTE_LANE_GAP)
    values.add(end + EDGE_ROUTE_LANE_GAP)
  })

  return Array.from(values)
    .filter(Number.isFinite)
    .sort((a, b) => Math.abs(a - midpoint) - Math.abs(b - midpoint))
    .slice(0, 18)
}

function compactPathPoints(points: Point[]) {
  const compact: Point[] = []
  points.forEach((point) => {
    const prev = compact[compact.length - 1]
    if (!prev || prev.x !== point.x || prev.y !== point.y) compact.push(point)
  })
  return compact
}

function scoreOrthogonalPath(points: Point[], obstacles: NodeBox[]) {
  let score = points.length * 18
  let intersections = 0
  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1]
    const end = points[index]
    score += Math.abs(end.x - start.x) + Math.abs(end.y - start.y)
    obstacles.forEach((box) => {
      if (segmentIntersectsBox(start, end, box)) {
        intersections += 1
        score += 1_000_000
      }
    })
  }
  score += intersections * intersections * 2_000_000
  return score
}

function segmentIntersectsBox(start: Point, end: Point, box: NodeBox) {
  if (start.x === end.x) {
    const minY = Math.min(start.y, end.y)
    const maxY = Math.max(start.y, end.y)
    return start.x >= box.x && start.x <= box.x + box.width && maxY >= box.y && minY <= box.y + box.height
  }
  if (start.y === end.y) {
    const minX = Math.min(start.x, end.x)
    const maxX = Math.max(start.x, end.x)
    return start.y >= box.y && start.y <= box.y + box.height && maxX >= box.x && minX <= box.x + box.width
  }
  return false
}

function inflateBox(box: NodeBox, padding: number) {
  return {
    x: box.x - padding,
    y: box.y - padding,
    width: box.width + padding * 2,
    height: box.height + padding * 2,
  }
}

function boxesOverlap(a: NodeBox, b: NodeBox) {
  return a.x <= b.x + b.width && a.x + a.width >= b.x && a.y <= b.y + b.height && a.y + a.height >= b.y
}

function getCorridorBox(a: NodeBox, b: NodeBox, padding: number) {
  const minX = Math.min(a.x, b.x) - padding
  const minY = Math.min(a.y, b.y) - padding
  const maxX = Math.max(a.x + a.width, b.x + b.width) + padding
  const maxY = Math.max(a.y + a.height, b.y + b.height) + padding
  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
  }
}

function boxDistanceToPoint(box: NodeBox, pointOrBox: Point | NodeBox) {
  const centerX = box.x + box.width / 2
  const centerY = box.y + box.height / 2
  const point = "width" in pointOrBox ? { x: pointOrBox.x + pointOrBox.width / 2, y: pointOrBox.y + pointOrBox.height / 2 } : pointOrBox
  return Math.abs(centerX - point.x) + Math.abs(centerY - point.y)
}

function getPathLabelPoint(points: Point[]) {
  if (points.length <= 2) return points[Math.max(0, points.length - 1)]
  const segments = points.slice(1).map((point, index) => ({
    start: points[index],
    end: point,
    length: Math.abs(point.x - points[index].x) + Math.abs(point.y - points[index].y),
  }))
  const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0)
  let cursor = 0
  for (const segment of segments) {
    if (cursor + segment.length >= totalLength / 2) {
      const remaining = totalLength / 2 - cursor
      const ratio = segment.length ? remaining / segment.length : 0
      return {
        x: segment.start.x + (segment.end.x - segment.start.x) * ratio,
        y: segment.start.y + (segment.end.y - segment.start.y) * ratio,
      }
    }
    cursor += segment.length
  }
  return points[Math.floor(points.length / 2)]
}

function pointsToPath(points: Point[]) {
  const [first, ...rest] = points
  return `M${first.x} ${first.y} ${rest.map((point) => `L${point.x} ${point.y}`).join(" ")}`
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function average(values: number[]) {
  if (!values.length) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
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

function getViewportForNode(node: Node | undefined, container: HTMLDivElement | null, preferredZoom = 1) {
  if (!node) return null
  const width = container?.clientWidth || 960
  const height = container?.clientHeight || 560
  if (!width || !height) return null
  const box = getNodeBox(node)
  const zoom = Math.max(0.18, Math.min(1.18, preferredZoom || 1))
  return {
    x: width / 2 - (box.x + box.width / 2) * zoom,
    y: height / 2 - (box.y + box.height / 2) * zoom,
    zoom,
  }
}

function selectCanvasRelationships(relations: GraphRelation[], selectedNodeId: string | null, viewMode: GraphViewMode, degreeById: Map<string, number>) {
  const edgeLimit = CANVAS_EDGE_LIMITS[viewMode] ?? 24
  const contextLimit = CANVAS_CONTEXT_EDGE_LIMITS[viewMode] ?? 0
  if (!selectedNodeId) {
    return [...relations]
      .sort((a, b) => getRelationPriority(b, selectedNodeId, degreeById) - getRelationPriority(a, selectedNodeId, degreeById))
      .slice(0, edgeLimit)
  }

  const focused = relations
    .filter((relation) => relation.source_id === selectedNodeId || relation.target_id === selectedNodeId)
    .sort((a, b) => getRelationPriority(b, selectedNodeId, degreeById) - getRelationPriority(a, selectedNodeId, degreeById))
    .slice(0, edgeLimit)

  const seen = new Set(focused.map(getRelationKey))
  const context = contextLimit
    ? relations
        .filter((relation) => !seen.has(getRelationKey(relation)))
        .sort((a, b) => getRelationPriority(b, selectedNodeId, degreeById) - getRelationPriority(a, selectedNodeId, degreeById))
        .slice(0, Math.max(0, edgeLimit - focused.length, contextLimit))
    : []

  return focused.concat(context)
}

function selectCanvasNodes(nodes: Node[], relationNodeIds: Set<string>, selectedNodeId: string | null, viewMode: GraphViewMode) {
  if (viewMode === "overview") return nodes
  if (viewMode === "formulaTheorem") {
    return selectFormulaCanvasNodes(nodes, relationNodeIds, selectedNodeId)
  }
  if (viewMode === "chapterPath") return nodes
  const visibleIds = new Set(relationNodeIds)
  if (selectedNodeId) visibleIds.add(selectedNodeId)

  const selected = nodes.filter((node) => visibleIds.has(node.id))
  const fallbackLimit = viewMode === "explore" ? 6 : 10
  const fallback = nodes.filter((node) => !visibleIds.has(node.id)).slice(0, Math.max(0, fallbackLimit - selected.length))
  return selected.concat(fallback)
}

function selectFormulaCanvasNodes(nodes: Node[], relationNodeIds: Set<string>, selectedNodeId: string | null) {
  const formulaNodes = nodes.filter((node) => FORMULA_CONTEXT_TYPES.has(String(node.data?.nodeType || "")))
  const visibleIds = new Set<string>()
  formulaNodes.forEach((node) => {
    if (visibleIds.size < FORMULA_CANVAS_NODE_LIMIT) visibleIds.add(node.id)
  })
  relationNodeIds.forEach((id) => {
    if (visibleIds.size < FORMULA_CANVAS_NODE_LIMIT) visibleIds.add(id)
  })
  if (selectedNodeId && nodes.some((node) => node.id === selectedNodeId && FORMULA_CONTEXT_TYPES.has(String(node.data?.nodeType || "")))) {
    visibleIds.add(selectedNodeId)
  }

  const selected = nodes.filter((node) => visibleIds.has(node.id)).sort((a, b) => getFormulaNodePriority(b, selectedNodeId) - getFormulaNodePriority(a, selectedNodeId))
  const selectedIds = new Set(selected.map((node) => node.id))
  const context = nodes
    .filter((node) => !selectedIds.has(node.id) && !FORMULA_CONTEXT_TYPES.has(String(node.data?.nodeType || "")))
    .slice(0, Math.max(0, 10 - selected.length))

  return selected.concat(context).slice(0, FORMULA_CANVAS_NODE_LIMIT)
}

function getFormulaNodePriority(node: Node, selectedNodeId: string | null) {
  if (selectedNodeId && node.id === selectedNodeId) return 10_000
  const type = String(node.data?.nodeType || "")
  const typeWeight: Record<string, number> = {
    formula: 900,
    theorem: 860,
    table: 760,
    note: 620,
  }
  return typeWeight[type] || 100
}

function createFlowEdges(relations: GraphRelation[], selectedNodeId: string | null): Edge[] {
  return relations
    .filter((relation) => relation.source_id && relation.target_id)
    .map((relation, index) => {
      const isFocused = !!selectedNodeId && (relation.source_id === selectedNodeId || relation.target_id === selectedNodeId)
      const shouldShowLabel = isFocused && index < CANVAS_LABEL_LIMIT
      return {
        id: relation.id || `${relation.source_id}-${relation.relation_type || "related"}-${relation.target_id}-${index}`,
        source: relation.source_id,
        target: relation.target_id,
        sourceHandle: "source",
        targetHandle: "target",
        label: shouldShowLabel ? relation.relation_type : undefined,
        type: "smoothstep",
        animated: isFocused,
        zIndex: isFocused ? 1 : 0,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: isFocused ? "#2563eb" : "#64748b",
          width: 14,
          height: 14,
        },
        className: isFocused ? "kg-flow-edge kg-flow-edge-focused" : "kg-flow-edge",
        style: {
          stroke: isFocused ? "#2563eb" : "#64748b",
          strokeDasharray: isFocused ? undefined : "5 8",
          strokeLinecap: "round",
          strokeWidth: isFocused ? 2.4 : 1.5,
          opacity: selectedNodeId ? (isFocused ? 0.96 : 0.36) : 0.62,
        },
        labelStyle: { fill: "#1d4ed8", fontSize: 11, fontWeight: 600 },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.94 },
        labelBgPadding: [5, 2] as [number, number],
        labelBgBorderRadius: 6,
      }
    })
}

function truncateRelationLabel(label: string) {
  return label.length > 18 ? `${label.slice(0, 17)}...` : label
}

function getRelationKey(relation: GraphRelation) {
  return relation.id || `${relation.source_id}:${relation.relation_type || "related"}:${relation.target_id}`
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

function layoutFormulaGridNodes(nodes: Node[], focusNodeId: string | null, edges: Edge[]) {
  if (!nodes.length) return []
  const focusNode = focusNodeId ? nodes.find((node) => node.id === focusNodeId) : undefined
  const focusRelatedIds = new Set<string>()
  if (focusNodeId) {
    edges.forEach((edge) => {
      if (edge.source === focusNodeId) focusRelatedIds.add(edge.target)
      if (edge.target === focusNodeId) focusRelatedIds.add(edge.source)
    })
  }
  const scoreNode = (node: Node) => {
    if (focusNodeId && node.id === focusNodeId) return 1_000_000
    let score = getFormulaNodePriority(node, focusNodeId)
    if (focusRelatedIds.has(node.id)) score += 12_000
    return score
  }
  const formulaNodes = nodes
    .filter((node) => node.id !== focusNodeId && FORMULA_CONTEXT_TYPES.has(String(node.data?.nodeType || "")))
    .sort((a, b) => scoreNode(b) - scoreNode(a))
  const contextNodes = nodes
    .filter((node) => node.id !== focusNodeId && !FORMULA_CONTEXT_TYPES.has(String(node.data?.nodeType || "")))
    .sort((a, b) => scoreNode(b) - scoreNode(a))
  const orderedNodes = [...(focusNode ? [focusNode] : []), ...formulaNodes, ...contextNodes]
  const xGap = FLOW_NODE_WIDTH + 148
  const yGap = FLOW_NODE_HEIGHT + 118

  if (!focusNode) {
    const columns = Math.max(2, Math.min(6, Math.ceil(Math.sqrt(Math.max(1, orderedNodes.length)))))
    return orderedNodes.map((node, index) => ({
      ...node,
      position: {
        x: (index % columns) * xGap,
        y: Math.floor(index / columns) * yGap,
      },
    }))
  }

  const cells = getCenteredFormulaCells(orderedNodes.length, xGap, yGap)

  return orderedNodes.map((node, index) => {
    const cell = cells[index] || { x: 0, y: 0 }
    return {
      ...node,
      position: cell,
    }
  })
}

function getCenteredFormulaCells(count: number, xGap: number, yGap: number) {
  let columns = Math.max(3, Math.min(7, Math.ceil(Math.sqrt(Math.max(1, count)))))
  if (columns % 2 === 0) columns += 1
  let rows = Math.max(3, Math.ceil(count / columns))
  if (rows % 2 === 0) rows += 1
  while (rows * columns < count) rows += 2
  const centerColumn = Math.floor(columns / 2)
  const centerRow = Math.floor(rows / 2)
  const cells: Array<{ x: number; y: number; row: number; col: number; distance: number }> = []

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < columns; col += 1) {
      const distance = Math.abs(row - centerRow) + Math.abs(col - centerColumn)
      cells.push({
        x: (col - centerColumn) * xGap,
        y: (row - centerRow) * yGap,
        row,
        col,
        distance,
      })
    }
  }

  return cells
    .sort((a, b) => {
      const distanceDelta = a.distance - b.distance
      if (distanceDelta) return distanceDelta
      const rowDelta = Math.abs(a.row - centerRow) - Math.abs(b.row - centerRow)
      if (rowDelta) return rowDelta
      return Math.abs(a.col - centerColumn) - Math.abs(b.col - centerColumn)
    })
    .slice(0, count)
    .map(({ x, y }) => ({ x, y }))
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

function getLayoutSignature(nodes: Node[], edges: Edge[], selectedNodeId: string | null, viewMode: GraphViewMode, layoutMode: GraphLayoutMode) {
  const nodePart = nodes.map((node) => node.id).sort().join(",")
  const edgePart = edges.map((edge) => `${edge.source}->${edge.target}:${edge.id}`).sort().join(",")
  return `${viewMode}|${layoutMode}|${selectedNodeId || ""}|${nodePart}|${edgePart}`
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
  onPrepare,
  onSelectNode,
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
  onPrepare: () => void
  onSelectNode: (nodeId: string) => void
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
      <button
        type="button"
        onClick={onPrepare}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm font-medium hover:bg-muted"
      >
        <ClipboardList size={15} />
        用该节点备课
      </button>

      <section className="rounded-lg border bg-muted/40 p-3">
        <h3 className="mb-2 text-sm font-semibold">学习建议</h3>
        <div className="space-y-2 text-sm text-muted-foreground">
          <p>{buildLearningAdvice(node, prerequisites.length, nextNodes.length, formulas.length)}</p>
          <RelationList title="前置知识" nodes={prerequisites.slice(0, 5)} empty="暂无明确前置节点" onSelectNode={onSelectNode} />
          <RelationList title="下一步节点" nodes={nextNodes.slice(0, 5)} empty="暂无明确后续节点" onSelectNode={onSelectNode} />
          <RelationList title="相关公式/定理/例题" nodes={relationsToNodes(formulas.concat(examples), nodeById, node.id).slice(0, 6)} empty="暂无相关公式或例题" onSelectNode={onSelectNode} />
        </div>
      </section>

      <section className="rounded-lg border bg-background p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">关系明细</h3>
          <span className="text-xs text-muted-foreground">{related.length} 条</span>
        </div>
        <div className="space-y-3">
          <RelationDetailList title="指向当前节点" selectedNodeId={node.id} relations={incoming.slice(0, 12)} nodeById={nodeById} empty="暂无入边" onSelectNode={onSelectNode} />
          <RelationDetailList title="从当前节点指出" selectedNodeId={node.id} relations={outgoing.slice(0, 12)} nodeById={nodeById} empty="暂无出边" onSelectNode={onSelectNode} />
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

function RelationList({ title, nodes, empty, onSelectNode }: { title: string; nodes: GraphNode[]; empty: string; onSelectNode: (nodeId: string) => void }) {
  return (
    <div>
      <div className="text-xs font-medium text-foreground">{title}</div>
      {nodes.length ? (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {nodes.map((node) => (
            <button
              key={node.id}
              type="button"
              onClick={() => onSelectNode(node.id)}
              className="rounded-md border bg-background px-2 py-1 text-left text-xs text-foreground hover:border-primary hover:text-primary"
            >
              {truncateLabel(node.label || node.id, 28)}
            </button>
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
  onSelectNode,
}: {
  title: string
  selectedNodeId: string
  relations: GraphRelation[]
  nodeById: Map<string, GraphNode>
  empty: string
  onSelectNode: (nodeId: string) => void
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
                  {otherNode ? (
                    <button
                      type="button"
                      onClick={() => onSelectNode(otherNode.id)}
                      className="text-left text-foreground underline-offset-2 hover:text-primary hover:underline"
                    >
                      {truncateLabel(otherNode.label || otherId, 36)}
                    </button>
                  ) : (
                    <span className="text-foreground">{truncateLabel(otherId, 36)}</span>
                  )}
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

function getOrderedChapterNodes(nodes: GraphNode[], filteredNodeIds: Set<string>) {
  const chapters = nodes.filter((node) => isStructuralHubNode(node))
  const filteredChapters = chapters.filter((node) => filteredNodeIds.has(node.id))
  return (filteredChapters.length ? filteredChapters : chapters).sort(compareChapterNodes)
}

function getChapterPathAnchorNodeId(
  selectedNodeId: string | null,
  rawNodes: GraphNode[],
  filteredNodeIds: Set<string>,
  relations: GraphRelation[],
  nodeById: Map<string, GraphNode>,
) {
  if (selectedNodeId && isStructuralHubNode(nodeById.get(selectedNodeId))) return selectedNodeId
  if (selectedNodeId) {
    const containingChapterId = findContainingChapterId(selectedNodeId, relations, nodeById)
    if (containingChapterId) return containingChapterId
  }
  return getOrderedChapterNodes(rawNodes, filteredNodeIds)[0]?.id || null
}

function findContainingChapterId(nodeId: string | null, relations: GraphRelation[], nodeById: Map<string, GraphNode>) {
  if (!nodeId) return null
  const directNode = nodeById.get(nodeId)
  if (isStructuralHubNode(directNode)) return nodeId

  const parentByChild = new Map<string, string[]>()
  relations.forEach((relation) => {
    if (!STRUCTURAL_RELATION_TYPES.has(relation.relation_type || "")) return
    if (!parentByChild.has(relation.target_id)) parentByChild.set(relation.target_id, [])
    parentByChild.get(relation.target_id)?.push(relation.source_id)
  })

  const queue = [nodeId]
  const visited = new Set<string>()
  while (queue.length) {
    const currentId = queue.shift()
    if (!currentId || visited.has(currentId)) continue
    visited.add(currentId)
    const node = nodeById.get(currentId)
    if (isStructuralHubNode(node)) return currentId
    ;(parentByChild.get(currentId) || []).forEach((parentId) => {
      if (!visited.has(parentId)) queue.push(parentId)
    })
  }
  return null
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
  const anchorNodeId =
    viewMode === "chapterPath"
      ? getChapterPathAnchorNodeId(selectedNodeId, rawNodes, filteredNodeIds, filteredRelations, nodeById)
      : getAnchorNodeId(selectedNodeId, recommendedNodes, nodeById)

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
    if (viewMode === "chapterPath") {
      return {
        nodes: [],
        relationships: [],
        anchorNodeId,
      }
    }
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
    return buildPathSubgraph(anchorNodeId, rawNodes, filteredNodeIds, filteredRelations, expandedNodeIds, selectedNeighborIds, degreeById, limit)
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

function createChapterOrderRelations(chapterNodes: GraphNode[]): GraphRelation[] {
  return chapterNodes.slice(0, -1).map((node, index) => {
    const nextNode = chapterNodes[index + 1]
    return {
      id: `chapter-path::${node.id}::${nextNode.id}`,
      source_id: node.id,
      target_id: nextNode.id,
      source: node.id,
      target: nextNode.id,
      source_node: node.id,
      target_node: nextNode.id,
      relation_type: "precedes",
      type: "precedes",
      similarity: 1,
      description: "chapter order",
      reviewed: true,
      metadata: { synthetic: true, role: "chapter_order" },
    }
  })
}

function getChapterInternalPath(
  chapterId: string,
  containsRelations: GraphRelation[],
  pathRelations: GraphRelation[],
  nodeById: Map<string, GraphNode>,
  limit: number,
) {
  const chapterKey = getNodeChapterKey(nodeById.get(chapterId)) || chapterId.replace(/^chapter::/, "")
  const directChildIds = new Set(containsRelations.filter((relation) => relation.source_id === chapterId).map((relation) => relation.target_id))
  const descendantIds = getChapterDescendantIds(chapterId, containsRelations, nodeById)
  const chapterNodeIds = new Set<string>([...directChildIds, ...descendantIds])

  nodeById.forEach((node) => {
    if (getNodeChapterKey(node) === chapterKey && CHAPTER_PATH_INTERNAL_TYPES.has(node.type || "")) {
      chapterNodeIds.add(node.id)
    }
  })

  const internalPathRelations = pathRelations.filter((relation) => chapterNodeIds.has(relation.source_id) && chapterNodeIds.has(relation.target_id))
  const orderedIds = getOrderedIdsFromPathRelations(internalPathRelations, chapterNodeIds)
  const preferredIds = orderedIds.length ? orderedIds : Array.from(chapterNodeIds).sort((a, b) => compareChapterPathNodeIds(a, b, nodeById))
  const selectedIds = preferredIds
    .filter((id) => {
      const node = nodeById.get(id)
      return node && id !== chapterId && CHAPTER_PATH_INTERNAL_TYPES.has(node.type || "")
    })
    .slice(0, Math.max(0, limit))
  const selectedIdSet = new Set(selectedIds)
  const selectedRelations = internalPathRelations.filter((relation) => selectedIdSet.has(relation.source_id) && selectedIdSet.has(relation.target_id))

  if (selectedRelations.length || !selectedIds.length) {
    return {
      nodeIds: new Set(selectedIds),
      relations: selectedRelations,
    }
  }

  return {
    nodeIds: new Set(selectedIds),
    relations: selectedIds.slice(0, -1).map((id, index) => createSyntheticInternalPathRelation(id, selectedIds[index + 1])),
  }
}

function getChapterDescendantIds(chapterId: string, containsRelations: GraphRelation[], nodeById: Map<string, GraphNode>) {
  const childrenByParent = new Map<string, string[]>()
  containsRelations.forEach((relation) => {
    if (!childrenByParent.has(relation.source_id)) childrenByParent.set(relation.source_id, [])
    childrenByParent.get(relation.source_id)?.push(relation.target_id)
  })

  const ids = new Set<string>()
  const queue = [...(childrenByParent.get(chapterId) || [])]
  while (queue.length) {
    const nodeId = queue.shift()
    if (!nodeId || ids.has(nodeId)) continue
    ids.add(nodeId)
    if (isStructuralHubNode(nodeById.get(nodeId))) continue
    ;(childrenByParent.get(nodeId) || []).forEach((childId) => {
      if (!ids.has(childId)) queue.push(childId)
    })
  }
  return ids
}

function getOrderedIdsFromPathRelations(pathRelations: GraphRelation[], allowedIds: Set<string>) {
  const outgoing = new Map<string, string[]>()
  const incomingCount = new Map<string, number>()
  allowedIds.forEach((id) => incomingCount.set(id, 0))
  pathRelations.forEach((relation) => {
    if (!allowedIds.has(relation.source_id) || !allowedIds.has(relation.target_id)) return
    if (!outgoing.has(relation.source_id)) outgoing.set(relation.source_id, [])
    outgoing.get(relation.source_id)?.push(relation.target_id)
    incomingCount.set(relation.target_id, (incomingCount.get(relation.target_id) || 0) + 1)
  })

  const starts = Array.from(allowedIds).filter((id) => (incomingCount.get(id) || 0) === 0 && (outgoing.get(id)?.length || 0) > 0)
  const ordered: string[] = []
  const seen = new Set<string>()
  const walk = (startId: string) => {
    let currentId: string | undefined = startId
    while (currentId && !seen.has(currentId)) {
      seen.add(currentId)
      ordered.push(currentId)
      currentId = (outgoing.get(currentId) || []).find((nextId) => !seen.has(nextId))
    }
  }
  starts.sort((a, b) => compareChapterPathNodeIds(a, b, new Map())).forEach(walk)
  pathRelations.forEach((relation) => {
    if (!seen.has(relation.source_id)) walk(relation.source_id)
    if (!seen.has(relation.target_id)) walk(relation.target_id)
  })
  return ordered
}

function createSyntheticInternalPathRelation(sourceId: string, targetId: string): GraphRelation {
  return {
    id: `chapter-internal-path::${sourceId}::${targetId}`,
    source_id: sourceId,
    target_id: targetId,
    source: sourceId,
    target: targetId,
    source_node: sourceId,
    target_node: targetId,
    relation_type: "precedes",
    type: "precedes",
    similarity: 1,
    description: "chapter internal order",
    reviewed: true,
    metadata: { synthetic: true, role: "chapter_internal_order" },
  }
}

function buildPathSubgraph(
  anchorNodeId: string,
  rawNodes: GraphNode[],
  filteredNodeIds: Set<string>,
  relations: GraphRelation[],
  expandedNodeIds: Set<string>,
  selectedNeighborIds: Set<string>,
  degreeById: Map<string, number>,
  limit: number,
) {
  const nodeById = new Map(rawNodes.map((node) => [node.id, node]))
  const chapterNodes = getOrderedChapterNodes(rawNodes, filteredNodeIds)
  const chapterNodeIds = new Set(chapterNodes.map((node) => node.id))
  const anchorChapterId = chapterNodeIds.has(anchorNodeId) ? anchorNodeId : findContainingChapterId(anchorNodeId, relations, nodeById) || chapterNodes[0]?.id || anchorNodeId
  const containsRelations = relations.filter((relation) => STRUCTURAL_RELATION_TYPES.has(relation.relation_type || ""))
  const pathRelations = relations.filter((relation) => PATH_RELATION_TYPES.has(relation.relation_type || ""))
  const expandedChapterIds = new Set<string>()
  expandedNodeIds.forEach((id) => {
    const chapterId = chapterNodeIds.has(id) ? id : findContainingChapterId(id, relations, nodeById)
    if (chapterId && chapterNodeIds.has(chapterId)) expandedChapterIds.add(chapterId)
  })

  if (!expandedChapterIds.size) {
    const nodeIds = new Set(chapterNodes.map((node) => node.id))
    return finalizeSubgraph({
      nodeIds,
      relations: createChapterOrderRelations(chapterNodes),
      rawNodes,
      filteredNodeIds,
      anchorNodeId: anchorChapterId,
      selectedNeighborIds,
      degreeById,
      relationshipLimit: FOCUSED_EDGE_LIMIT,
      nodeLimit: Math.max(limit, chapterNodes.length),
    })
  }

  const nodeIds = new Set<string>()
  expandedChapterIds.forEach((chapterId) => nodeIds.add(chapterId))
  const expandedRelations: GraphRelation[] = []
  const expandedNodeLimit = Math.max(limit, expandedChapterIds.size + 56)
  expandedChapterIds.forEach((chapterId) => {
    const chapterPath = getChapterInternalPath(chapterId, containsRelations, pathRelations, nodeById, expandedNodeLimit - nodeIds.size)
    chapterPath.nodeIds.forEach((id) => {
      if (nodeIds.size < expandedNodeLimit) nodeIds.add(id)
    })
    expandedRelations.push(...chapterPath.relations)
  })

  return finalizeSubgraph({
    nodeIds,
    relations: expandedRelations,
    rawNodes,
    filteredNodeIds,
    anchorNodeId: anchorChapterId,
    selectedNeighborIds,
    degreeById,
    relationshipLimit: FOCUSED_EDGE_LIMIT,
    nodeLimit: expandedNodeLimit,
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
  const formulaContextNodes = rawNodes
    .filter((node) => FORMULA_CONTEXT_TYPES.has(node.type || "") && filteredNodeIds.has(node.id))
    .sort((a, b) => getNodeScore(b, degreeById) - getNodeScore(a, degreeById))
    .slice(0, Math.min(34, FORMULA_CANVAS_NODE_LIMIT, limit))

  formulaContextNodes.forEach((node) => {
    if (nodeIds.size < limit) nodeIds.add(node.id)
  })

  const formulaContextIds = new Set(formulaContextNodes.map((node) => node.id))
  formulaRelations
    .filter((relation) => formulaContextIds.has(relation.source_id) || formulaContextIds.has(relation.target_id))
    .sort((a, b) => getRelationPriority(b, anchorNodeId, degreeById) - getRelationPriority(a, anchorNodeId, degreeById))
    .slice(0, 36)
    .forEach((relation) => {
      if (nodeIds.size < limit) nodeIds.add(relation.source_id)
      if (nodeIds.size < limit) nodeIds.add(relation.target_id)
    })

  const directFormulaRelations = getTopRelationsForNode(anchorNodeId, formulaRelations, degreeById, 26)
  directFormulaRelations.forEach((relation) => {
    if (nodeIds.size < limit) {
      nodeIds.add(relation.source_id)
      nodeIds.add(relation.target_id)
    }
  })

  const formulaIds = new Set(
    Array.from(nodeIds).filter((id) => {
      const type = rawNodes.find((node) => node.id === id)?.type || ""
      return FORMULA_CONTEXT_TYPES.has(type)
    }),
  )

  formulaIds.forEach((formulaId) => {
    getTopRelationsForNode(formulaId, formulaRelations.concat(semanticRelations), degreeById, 3).forEach((relation) => {
      if (nodeIds.size < limit) {
        nodeIds.add(relation.source_id)
        nodeIds.add(relation.target_id)
      }
    })
  })

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

  const finalNodes = keptNodes
    .sort((a, b) => getVisibleNodePriority(b, anchorNodeId, selectedNeighborIds, degreeById) - getVisibleNodePriority(a, anchorNodeId, selectedNeighborIds, degreeById))
    .slice(0, nodeLimit)
  const finalNodeIds = new Set(finalNodes.map((node) => node.id))
  const finalRelationships = keptRelations.filter((relation) => finalNodeIds.has(relation.source_id) && finalNodeIds.has(relation.target_id))

  return {
    nodes: finalNodes,
    relationships: finalRelationships,
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

function compareChapterNodes(a: GraphNode, b: GraphNode) {
  const chapterDelta = getChapterSortValue(a) - getChapterSortValue(b)
  if (chapterDelta) return chapterDelta
  return (a.label || a.id).localeCompare(b.label || b.id)
}

function getChapterSortValue(node: GraphNode) {
  const key = getNodeChapterKey(node) || node.id || node.label || ""
  const appendixMatch = key.match(/appendix\s*([0-9]+)/i) || key.match(/appendix([0-9]+)/i)
  if (appendixMatch) return 10_000 + Number(appendixMatch[1])
  const chapterMatch = key.match(/chapter\s*([0-9]+)/i) || key.match(/chapter([0-9]+)/i) || key.match(/(?:^|::)([0-9]+)$/)
  if (chapterMatch) return Number(chapterMatch[1])
  return Number.MAX_SAFE_INTEGER
}

function compareChapterPathNodeIds(leftId: string, rightId: string, nodeById: Map<string, GraphNode>) {
  const leftNode = nodeById.get(leftId)
  const rightNode = nodeById.get(rightId)
  const leftUnit = getSourceUnitSortValue(leftNode, leftId)
  const rightUnit = getSourceUnitSortValue(rightNode, rightId)
  if (leftUnit !== rightUnit) return leftUnit - rightUnit
  const leftIndex = getBlockIndexSortValue(leftNode, leftId)
  const rightIndex = getBlockIndexSortValue(rightNode, rightId)
  if (leftIndex !== rightIndex) return leftIndex - rightIndex
  return leftId.localeCompare(rightId)
}

function getSourceUnitSortValue(node: GraphNode | undefined, fallback: string) {
  const metadata = node?.metadata || {}
  const sourceUnit = String(metadata.source_unit || metadata.source || metadata.source_file || fallback)
  const match = sourceUnit.match(/(?:chapter|appendix)\d+[_-](\d+)/i) || fallback.match(/(?:chapter|appendix)\d+[_-](\d+)/i)
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER
}

function getBlockIndexSortValue(node: GraphNode | undefined, fallback: string) {
  const blockIndex = node?.metadata?.block_index
  if (typeof blockIndex === "number" && Number.isFinite(blockIndex)) return blockIndex
  if (typeof blockIndex === "string" && Number.isFinite(Number(blockIndex))) return Number(blockIndex)
  const match = fallback.match(/::(\d+)$/)
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER
}

function getNodeChapterKey(node: GraphNode | undefined) {
  if (!node) return ""
  const metadataChapter = typeof node.metadata?.chapter === "string" ? node.metadata.chapter.trim() : ""
  if (metadataChapter) return metadataChapter.replace(/^chapter::/, "")
  const id = node.id || ""
  const chapterMatch = id.match(/chapter::([^:]+)/) || id.match(/(?:block|section|formula|table|example)::((?:chapter|appendix)[^_:]+)/)
  if (chapterMatch) return chapterMatch[1]
  return ""
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

function isStructuralHubNode(node: GraphNode | undefined) {
  return (node?.type || "") === "chapter"
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
