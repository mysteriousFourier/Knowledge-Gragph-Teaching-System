import { useQuery } from "@tanstack/react-query"
import { maintenanceClient } from "./client"
import type { ApiResponse } from "@/types/api"
import type { GraphNode, GraphRelation, GraphData } from "@/types/graph"

type MetadataRecord = Record<string, unknown>

const normalizeMetadata = (value: unknown): MetadataRecord => {
  if (!value) return {}
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as MetadataRecord) : {}
    } catch {
      return {}
    }
  }
  return typeof value === "object" && !Array.isArray(value) ? (value as MetadataRecord) : {}
}

const firstString = (...values: unknown[]) => {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return ""
}

const endpointString = (value: unknown) => {
  if (value && typeof value === "object") {
    const record = value as MetadataRecord
    return firstString(record.id, record.node_id, record.nodeId, record.value, record.label)
  }
  if (value === null || value === undefined) return ""
  const text = String(value).trim()
  return text && text !== "undefined" && text !== "null" ? text : ""
}

const firstEndpoint = (...values: unknown[]) => {
  for (const value of values) {
    const endpoint = endpointString(value)
    if (endpoint) return endpoint
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

const normalizeNode = (node: GraphNode): GraphNode => {
  const metadata = normalizeMetadata((node as { metadata?: unknown }).metadata)
  return {
    ...node,
    label: node.label || firstString(metadata.label) || node.id,
    type: node.type || "concept",
    confidence: typeof node.confidence === "number" ? node.confidence : firstNumber(metadata.confidence),
    reviewed: Boolean(node.reviewed ?? metadata.reviewed),
    metadata,
  }
}

const normalizeRelation = (relation: GraphRelation): GraphRelation => {
  const metadata = normalizeMetadata((relation as { metadata?: unknown; properties?: unknown }).metadata || (relation as { properties?: unknown }).properties)
  const sourceId = firstEndpoint(
    relation.source_id,
    relation.source,
    relation.source_node,
    relation.sourceId,
    relation.sourceNode,
    relation.from,
    metadata.source_id,
    metadata.source,
    metadata.source_node,
    metadata.sourceId,
    metadata.sourceNode,
    metadata.from,
  )
  const targetId = firstEndpoint(
    relation.target_id,
    relation.target,
    relation.target_node,
    relation.targetId,
    relation.targetNode,
    relation.to,
    metadata.target_id,
    metadata.target,
    metadata.target_node,
    metadata.targetId,
    metadata.targetNode,
    metadata.to,
  )
  const relationType = firstEndpoint(relation.relation_type, relation.type, relation.label, metadata.relation_type, metadata.type, metadata.label) || "related"
  const description = firstString(relation.description, metadata.description)

  return {
    ...relation,
    source_id: sourceId,
    target_id: targetId,
    source: sourceId,
    target: targetId,
    source_node: sourceId,
    target_node: targetId,
    relation_type: relationType,
    type: relationType,
    similarity: firstNumber(relation.similarity, relation.strength, metadata.similarity, metadata.strength),
    description,
    reviewed: Boolean(relation.reviewed ?? metadata.reviewed),
    metadata,
  }
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

const getGraphNodes = (limit: number) =>
  maintenanceClient
    .get<ApiResponse<{ nodes: GraphNode[]; count: number }>>(
      `/api/maintenance/graph/nodes?limit=${encodeURIComponent(limit)}`,
    )
    .then((response) => response.data)

const getGraphRelationships = (limit: number, relationType?: string) => {
  const params = new URLSearchParams({ limit: String(limit) })
  if (relationType) params.set("relation_type", relationType)
  return maintenanceClient
    .get<ApiResponse<{ relationships: GraphRelation[]; count: number }>>(
      `/api/maintenance/graph/relationships?${params.toString()}`,
    )
    .then((response) => response.data)
}

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
      const payload = await getGraphNodes(limit)
      const nodes = (payload.data?.nodes || []).map(normalizeNode).filter((node) => !isLectureNode(node))
      return { success: payload.success, nodes, count: payload.data?.count ?? nodes.length }
    },
  })
}

export const useGraphRelationships = (limit = 10000, relationType?: string) => {
  return useQuery({
    queryKey: ["graph-relationships", limit, relationType || "all"],
    queryFn: async () => {
      const payload = await getGraphRelationships(limit, relationType)
      const normalizedRelations = (payload.data?.relationships || []).map(normalizeRelation)
      const completeEndpointRelations = normalizedRelations.filter((relation) => relation.source_id && relation.target_id)
      const relations = completeEndpointRelations
      const relationships = relations.slice(0, limit)
      return {
        success: payload.success,
        relationships,
        count: relations.length,
        rawCount: normalizedRelations.length,
        missingEndpointCount: normalizedRelations.length - completeEndpointRelations.length,
        missingNodeCount: 0,
      }
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
          return {
            ...payload,
            nodeId,
            relations: relations.map(normalizeRelation),
            count: payload.data?.count ?? payload.count ?? relations.length,
          }
        }),
    enabled: !!nodeId,
  })
}

export const useGraphStats = () => {
  return useQuery({
    queryKey: ["graph-stats"],
    queryFn: async () => {
      return maintenanceClient
        .get<ApiResponse<{ total_nodes: number; total_relationships: number; details?: unknown }> & {
          data?: { total_nodes: number; total_relationships: number; details?: unknown }
        }>("/api/maintenance/stats")
        .then((response) => response.data)
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
