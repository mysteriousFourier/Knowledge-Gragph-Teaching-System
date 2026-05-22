import { createSlice, type PayloadAction } from "@reduxjs/toolkit"

interface GraphState {
  selectedNodeId: string | null
  selectedRelationId: string | null
  searchQuery: string
  filterType: string | null
  layoutDirection: "TB" | "LR" | "RL" | "BT"
  zoomLevel: number
  showLabels: boolean
  nodeTypes: string[]
  relationTypes: string[]
}

const initialState: GraphState = {
  selectedNodeId: null,
  selectedRelationId: null,
  searchQuery: "",
  filterType: null,
  layoutDirection: "TB",
  zoomLevel: 1,
  showLabels: true,
  nodeTypes: [],
  relationTypes: [],
}

const graphSlice = createSlice({
  name: "graph",
  initialState,
  reducers: {
    selectNode: (state, action: PayloadAction<string | null>) => {
      state.selectedNodeId = action.payload
      state.selectedRelationId = null
    },
    selectRelation: (state, action: PayloadAction<string | null>) => {
      state.selectedRelationId = action.payload
      state.selectedNodeId = null
    },
    setSearchQuery: (state, action: PayloadAction<string>) => {
      state.searchQuery = action.payload
    },
    setFilterType: (state, action: PayloadAction<string | null>) => {
      state.filterType = action.payload
    },
    setLayoutDirection: (state, action: PayloadAction<GraphState["layoutDirection"]>) => {
      state.layoutDirection = action.payload
    },
    setZoomLevel: (state, action: PayloadAction<number>) => {
      state.zoomLevel = Math.max(0.1, Math.min(3, action.payload))
    },
    toggleLabels: (state) => {
      state.showLabels = !state.showLabels
    },
    setNodeTypes: (state, action: PayloadAction<string[]>) => {
      state.nodeTypes = action.payload
    },
    setRelationTypes: (state, action: PayloadAction<string[]>) => {
      state.relationTypes = action.payload
    },
    resetGraphView: (state) => {
      state.selectedNodeId = null
      state.selectedRelationId = null
      state.searchQuery = ""
      state.filterType = null
      state.zoomLevel = 1
    },
  },
})

export const {
  selectNode,
  selectRelation,
  setSearchQuery,
  setFilterType,
  setLayoutDirection,
  setZoomLevel,
  toggleLabels,
  setNodeTypes,
  setRelationTypes,
  resetGraphView,
} = graphSlice.actions
export default graphSlice.reducer
