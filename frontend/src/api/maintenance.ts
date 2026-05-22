import { useMutation, useQuery } from "@tanstack/react-query"
import { maintenanceClient } from "./client"
import type { ApiResponse } from "@/types/api"
import type { GraphNode, GraphRelation, AddNodeRequest, UpdateNodeRequest, AddRelationRequest } from "@/types/graph"

export const useMaintenanceGraph = () => {
  return useQuery({
    queryKey: ["maintenance-graph"],
    queryFn: () => maintenanceClient.get<ApiResponse<unknown>>("/api/maintenance/graph").then((r) => r.data),
  })
}

export const useSearchNodes = () => {
  return useMutation({
    mutationFn: (data: { query: string; node_type?: string; limit?: number }) =>
      maintenanceClient.post<ApiResponse<GraphNode[]>>("/api/maintenance/search-nodes", data).then((r) => r.data),
  })
}

export const useAddNode = () => {
  return useMutation({
    mutationFn: (data: AddNodeRequest) =>
      maintenanceClient.post<ApiResponse<GraphNode>>("/api/maintenance/add-node", data).then((r) => r.data),
  })
}

export const useUpdateNode = () => {
  return useMutation({
    mutationFn: (data: UpdateNodeRequest) =>
      maintenanceClient.put<ApiResponse<GraphNode>>("/api/maintenance/update-node", data).then((r) => r.data),
  })
}

export const useDeleteNode = () => {
  return useMutation({
    mutationFn: (nodeId: string) =>
      maintenanceClient
        .delete<ApiResponse<unknown>>(`/api/maintenance/delete-node?node_id=${nodeId}`)
        .then((r) => r.data),
  })
}

export const useAddRelation = () => {
  return useMutation({
    mutationFn: (data: AddRelationRequest) =>
      maintenanceClient.post<ApiResponse<GraphRelation>>("/api/maintenance/add-relation", data).then((r) => r.data),
  })
}

export const useAnalytics = () => {
  return useQuery({
    queryKey: ["analytics"],
    queryFn: () => maintenanceClient.get<ApiResponse<unknown>>("/api/maintenance/analytics").then((r) => r.data),
  })
}
