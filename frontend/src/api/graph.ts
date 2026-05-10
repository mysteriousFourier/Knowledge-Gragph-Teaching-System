import { useQuery } from "@tanstack/react-query"
import { maintenanceClient } from "./client"
import type { ApiResponse } from "@/types/api"
import type { GraphNode, GraphRelation, GraphData } from "@/types/graph"

const normalizeNode = (node: GraphNode): GraphNode => ({
  ...node,
  label: node.label || node.metadata?.label as string || node.id,
  type: node.type || "concept",
  confidence: typeof node.confidence === "number" ? node.confidence : 1,
  reviewed: Boolean(node.reviewed),
  metadata: node.metadata || {},
})

const firstString = (...values: unknown[]) => {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return ""
}

const firstNumber = (...values: unknown[]) => {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value)
  }
  return 1
}

const normalizeRelation = (relation: GraphRelation): GraphRelation => ({
  ...relation,
  source_id: firstString(
    relation.source_id,
    relation.source,
    relation.source_node,
    relation.sourceId,
    relation.sourceNode,
    relation.from,
    relation.metadata?.source_id,
    relation.metadata?.source,
    relation.metadata?.source_node,
    relation.metadata?.sourceId,
    relation.metadata?.sourceNode,
    relation.metadata?.from,
  ),
  target_id: firstString(
    relation.target_id,
    relation.target,
    relation.target_node,
    relation.targetId,
    relation.targetNode,
    relation.to,
    relation.metadata?.target_id,
    relation.metadata?.target,
    relation.metadata?.target_node,
    relation.metadata?.targetId,
    relation.metadata?.targetNode,
    relation.metadata?.to,
  ),
  relation_type: firstString(relation.relation_type, relation.type, relation.label, relation.metadata?.relation_type, relation.metadata?.type, relation.metadata?.label) || "related",
  similarity: firstNumber(relation.similarity, relation.strength, relation.metadata?.similarity, relation.metadata?.strength),
  description: firstString(relation.description, relation.metadata?.description),
  reviewed: Boolean(relation.reviewed),
  metadata: relation.metadata || {},
})

const graphRelations = (graph?: GraphData): GraphRelation[] => {
  const relations = graph?.relations
  if (Array.isArray(relations) && relations.length) return relations
  const edges = graph?.edges
  if (Array.isArray(edges)) return edges
  return []
}

const isLectureNode = (node: GraphNode) => {
  const metadata = node.metadata || {}
  const label = String(node.label || metadata.label || "")
  const id = String(node.id || "")
  const source = String(node.source || metadata.source || "")
  return id.endsWith("__lecture") || label.includes("授课文案") || (source === "frontend_test" && node.type === "observation")
}

const getGraph = () =>
  maintenanceClient.get<ApiResponse<GraphData>>("/api/maintenance/graph").then((response) => response.data)

export const useGraphData = () => {
  return useQuery({
    queryKey: ["graph-data"],
    queryFn: getGraph,
  })
}

export const useGraphNodes = (limit = 5000) => {
  return useQuery({
    queryKey: ["graph-nodes", limit],
    queryFn: async () => {
      const graph = await getGraph()
      const nodes = (graph.data?.nodes || []).map(normalizeNode).filter((node) => !isLectureNode(node))
      return { success: graph.success, nodes: nodes.slice(0, limit), count: nodes.length }
    },
  })
}

export const useGraphRelationships = (limit = 10000) => {
  return useQuery({
    queryKey: ["graph-relationships", limit],
    queryFn: async () => {
      const graph = await getGraph()
      const visibleNodeIds = new Set((graph.data?.nodes || []).map(normalizeNode).filter((node) => !isLectureNode(node)).map((node) => node.id))
      const relations = graphRelations(graph.data)
        .map(normalizeRelation)
        .filter((relation) => visibleNodeIds.has(relation.source_id) && visibleNodeIds.has(relation.target_id))
      const relationships = relations.slice(0, limit)
      return { success: graph.success, relationships, count: relations.length }
    },
  })
}

export const useGraphNode = (nodeId: string) => {
  return useQuery({
    queryKey: ["graph-node", nodeId],
    queryFn: () =>
      maintenanceClient
        .get<ApiResponse<{ node: GraphNode }>>(`/api/node?node_id=${nodeId}`)
        .then((r) => r.data),
    enabled: !!nodeId,
  })
}

export const useGraphRelations = (nodeId: string) => {
  return useQuery({
    queryKey: ["graph-relations", nodeId],
    queryFn: () =>
      maintenanceClient
        .get<ApiResponse<{ relations: GraphRelation[]; count: number }> & { relations?: GraphRelation[]; count?: number }>(`/api/maintenance/relations?node_id=${encodeURIComponent(nodeId)}`)
        .then((r) => {
          const payload = r.data
          const relations = payload.data?.relations || payload.relations || []
          return { ...payload, relations: relations.map(normalizeRelation), count: payload.data?.count ?? payload.count ?? relations.length }
        }),
    enabled: !!nodeId,
  })
}

export const useGraphStats = () => {
  return useQuery({
    queryKey: ["graph-stats"],
    queryFn: async () => {
      const graph = await getGraph()
      const nodes = (graph.data?.nodes || []).map(normalizeNode).filter((node) => !isLectureNode(node))
      const visibleNodeIds = new Set(nodes.map((node) => node.id))
      const relations = graphRelations(graph.data)
        .map(normalizeRelation)
        .filter((relation) => visibleNodeIds.has(relation.source_id) && visibleNodeIds.has(relation.target_id))
      return {
        success: graph.success,
        data: {
          total_nodes: nodes.length,
          total_relationships: relations.length,
          details: graph.data?.stats || {},
        },
      }
    },
  })
}

export const useSearchLegacyNodes = (searchTerm: string) => {
  return useQuery({
    queryKey: ["search-legacy-nodes", searchTerm],
    queryFn: () =>
      maintenanceClient
        .get<{ success: boolean; nodes: GraphNode[]; count: number }>(`/api/search/${encodeURIComponent(searchTerm)}`)
        .then((r) => r.data),
    enabled: !!searchTerm,
  })
}
