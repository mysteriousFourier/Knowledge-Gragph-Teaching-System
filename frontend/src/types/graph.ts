export interface GraphNode {
  id: string
  label: string
  type: string
  content?: string
  source?: string
  confidence: number
  created_at?: string
  updated_at?: string
  reviewed: boolean
  metadata: Record<string, unknown>
}

export interface GraphRelation {
  id: string
  source_id: string
  target_id: string
  strength?: number
  source?: string
  target?: string
  source_node?: string
  target_node?: string
  sourceId?: string
  targetId?: string
  sourceNode?: string
  targetNode?: string
  from?: string
  to?: string
  type?: string
  label?: string
  relation_type: string
  similarity: number
  description: string
  source_file?: string
  created_at?: string
  updated_at?: string
  reviewed: boolean
  metadata: Record<string, unknown>
}

export interface GraphData {
  nodes: GraphNode[]
  relations: GraphRelation[]
  edges?: GraphRelation[]
  stats?: {
    node_count: number
    relation_count: number
  }
}

export interface AddNodeRequest {
  id?: string
  label: string
  type: string
  content?: string
  metadata?: Record<string, unknown>
}

export interface UpdateNodeRequest {
  node_id: string
  content?: string
  metadata?: Record<string, unknown>
}

export interface AddRelationRequest {
  source_id: string
  target_id: string
  relation_type: string
  similarity?: number
  metadata?: Record<string, unknown>
}
