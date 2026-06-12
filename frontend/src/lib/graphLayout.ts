import type { Edge, Node } from "@xyflow/react"

export type GraphLayoutMode = "elk" | "dagre" | "grid"

export interface LayoutOptions {
  mode: GraphLayoutMode
  direction?: "RIGHT" | "LEFT" | "DOWN" | "UP"
  nodeWidth?: number
  nodeHeight?: number
}

const DEFAULT_NODE_WIDTH = 220
const DEFAULT_NODE_HEIGHT = 70

export async function layoutGraphNodes(
  nodes: Node[],
  edges: Edge[],
  options: LayoutOptions,
): Promise<Node[]> {
  if (nodes.length === 0) return []
  const validEdges = getRenderableEdges(nodes, edges)

  if (options.mode === "elk") {
    try {
      return await layoutWithElk(nodes, validEdges, options)
    } catch (error) {
      console.warn("ELK layout failed, falling back to Dagre.", error)
    }
  }

  if (options.mode === "elk" || options.mode === "dagre") {
    try {
      return await layoutWithDagre(nodes, validEdges, options)
    } catch (error) {
      console.warn("Dagre layout failed, falling back to grid.", error)
    }
  }

  return layoutWithGrid(nodes, options)
}

async function layoutWithElk(nodes: Node[], edges: Edge[], options: LayoutOptions): Promise<Node[]> {
  const { default: ELK } = await import("elkjs/lib/elk.bundled.js")
  const elk = new ELK()
  const nodeWidth = options.nodeWidth ?? DEFAULT_NODE_WIDTH
  const nodeHeight = options.nodeHeight ?? DEFAULT_NODE_HEIGHT
  const elkGraph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": options.direction ?? "RIGHT",
      "elk.spacing.nodeNode": "78",
      "elk.layered.spacing.nodeNodeBetweenLayers": "118",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
      "elk.edgeRouting": "ORTHOGONAL",
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: getNodeDimension(node.style?.width, nodeWidth),
      height: getNodeDimension(node.style?.height, nodeHeight),
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  }

  const result = await elk.layout(elkGraph)
  const positions = new Map((result.children || []).map((node) => [node.id, { x: node.x || 0, y: node.y || 0 }]))
  return nodes.map((node) => ({
    ...node,
    position: positions.get(node.id) || node.position,
  }))
}

async function layoutWithDagre(nodes: Node[], edges: Edge[], options: LayoutOptions): Promise<Node[]> {
  const { graphlib, layout: dagreLayout } = await import("@dagrejs/dagre")
  const nodeWidth = options.nodeWidth ?? DEFAULT_NODE_WIDTH
  const nodeHeight = options.nodeHeight ?? DEFAULT_NODE_HEIGHT
  const graph = new graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({
    rankdir: getDagreDirection(options.direction),
    nodesep: 74,
    ranksep: 126,
    marginx: 40,
    marginy: 40,
  })

  nodes.forEach((node) => {
    graph.setNode(node.id, {
      width: getNodeDimension(node.style?.width, nodeWidth),
      height: getNodeDimension(node.style?.height, nodeHeight),
    })
  })
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))
  dagreLayout(graph)

  return nodes.map((node) => {
    const position = graph.node(node.id)
    return {
      ...node,
      position: {
        x: position.x - getNodeDimension(node.style?.width, nodeWidth) / 2,
        y: position.y - getNodeDimension(node.style?.height, nodeHeight) / 2,
      },
    }
  })
}

function layoutWithGrid(nodes: Node[], options: LayoutOptions): Node[] {
  const nodeWidth = options.nodeWidth ?? DEFAULT_NODE_WIDTH
  const nodeHeight = options.nodeHeight ?? DEFAULT_NODE_HEIGHT
  const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)))
  const xGap = nodeWidth + 76
  const yGap = nodeHeight + 72

  return nodes.map((node, index) => ({
    ...node,
    position: {
      x: (index % columns) * xGap,
      y: Math.floor(index / columns) * yGap,
    },
  }))
}

function getRenderableEdges(nodes: Node[], edges: Edge[]) {
  const nodeIds = new Set(nodes.map((node) => node.id))
  return edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
}

function getDagreDirection(direction: LayoutOptions["direction"]) {
  if (direction === "DOWN") return "TB"
  if (direction === "UP") return "BT"
  if (direction === "LEFT") return "RL"
  return "LR"
}

function getNodeDimension(value: unknown, fallback: number): number {
  if (typeof value === "number") return value
  if (typeof value === "string") {
    const parsed = Number.parseFloat(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}
