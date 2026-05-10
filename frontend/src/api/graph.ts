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

const normalizeRelation = (relation: GraphRelation): GraphRelation => ({
  ...relation,
  source_id: relation.source_id || (relation as unknown as { source?: string; source_node?: string }).source || (relation as unknown as { source_node?: string }).source_node || "",
  target_id: relation.target_id || (relation as unknown as { target?: string; target_node?: string }).target || (relation as unknown as { target_node?: string }).target_node || "",
  relation_type: relation.relation_type || (relation as unknown as { type?: string }).type || "related",
  similarity: typeof relation.similarity === "number" ? relation.similarity : 1,
  description: relation.description || "",
  reviewed: Boolean(relation.reviewed),
  metadata: relation.metadata || {},
})

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
      const relations = (graph.data?.relations || [])
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
        .get<ApiResponse<{ relations: GraphRelation[]; count: number }>>(`/api/relations?node_id=${nodeId}`)
        .then((r) => r.data),
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
      const relations = (graph.data?.relations || [])
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
