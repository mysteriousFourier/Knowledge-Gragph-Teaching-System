import { createFileRoute } from "@tanstack/react-router"
import { Network, Plus, Trash2, Edit3, Save } from "lucide-react"
import { useState } from "react"
import { useGraphNodes, useGraphStats } from "@/api/graph"
import { useAddNode, useUpdateNode, useDeleteNode } from "@/api/maintenance"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { EmptyState } from "@/components/common/EmptyState"
import { RichTextContent } from "@/components/renderers/RichTextContent"

export const Route = createFileRoute("/graph/admin")({
  component: GraphAdminPage,
})

function GraphAdminPage() {
  const [editingNode, setEditingNode] = useState<string | null>(null)
  const [editContent, setEditContent] = useState("")
  const [showAddForm, setShowAddForm] = useState(false)
  const [newNode, setNewNode] = useState({ label: "", type: "", content: "" })

  const { data: nodesData, isLoading } = useGraphNodes(100)
  const { data: statsData } = useGraphStats()
  const addNode = useAddNode()
  const updateNode = useUpdateNode()
  const deleteNode = useDeleteNode()

  const nodes = nodesData?.nodes || []
  const stats = statsData?.data

  const handleEdit = (nodeId: string, content: string) => {
    setEditingNode(nodeId)
    setEditContent(content)
  }

  const handleSave = async (nodeId: string) => {
    await updateNode.mutateAsync({ node_id: nodeId, content: editContent })
    setEditingNode(null)
  }

  const handleDelete = async (nodeId: string) => {
    if (confirm("确定要删除这个节点吗？")) {
      await deleteNode.mutateAsync(nodeId)
    }
  }

  const handleAdd = async () => {
    if (!newNode.label || !newNode.type) return
    await addNode.mutateAsync({
      label: newNode.label,
      type: newNode.type,
      content: newNode.content,
    })
    setNewNode({ label: "", type: "", content: "" })
    setShowAddForm(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">图谱管理</h1>
          <p className="text-muted-foreground">管理知识图谱节点和关系</p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="inline-flex w-full items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 sm:w-auto"
        >
          <Plus size={16} />
          添加节点
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="总节点数" value={stats.total_nodes} />
          <StatCard label="总关系数" value={stats.total_relationships} />
          <StatCard label="显示节点" value={nodes.length} />
          <StatCard label="图谱状态" value="正常" />
        </div>
      )}

      {/* Add Node Form */}
      {showAddForm && (
        <div className="bg-card border rounded-xl p-4">
          <h3 className="font-medium mb-3">添加新节点</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              value={newNode.label}
              onChange={(e) => setNewNode((prev) => ({ ...prev, label: e.target.value }))}
              placeholder="节点标签"
              className="px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
            <input
              value={newNode.type}
              onChange={(e) => setNewNode((prev) => ({ ...prev, type: e.target.value }))}
              placeholder="节点类型"
              className="px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                onClick={handleAdd}
                disabled={addNode.isPending}
                className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
              >
                {addNode.isPending ? "添加中..." : "添加"}
              </button>
              <button
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 bg-muted text-muted-foreground rounded-lg text-sm hover:bg-muted/80"
              >
                取消
              </button>
            </div>
          </div>
          <textarea
            value={newNode.content}
            onChange={(e) => setNewNode((prev) => ({ ...prev, content: e.target.value }))}
            placeholder="节点内容（可选）"
            className="w-full mt-3 px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary min-h-[80px] resize-y"
          />
        </div>
      )}

      {/* Nodes Table */}
      <div className="bg-card border rounded-xl overflow-hidden">
        <div className="p-4 border-b">
          <h2 className="font-semibold flex items-center gap-2">
            <Network size={18} />
            节点管理
          </h2>
        </div>

        {isLoading ? (
          <div className="p-8">
            <LoadingSpinner text="加载节点中..." />
          </div>
        ) : nodes.length === 0 ? (
          <div className="p-8">
            <EmptyState title="暂无节点" description="知识图谱中没有节点数据" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium">标签</th>
                  <th className="text-left px-4 py-3 font-medium">类型</th>
                  <th className="text-left px-4 py-3 font-medium">内容</th>
                  <th className="text-right px-4 py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {nodes.map((node) => (
                  <tr key={node.id} className="hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <span className="font-medium">{node.label}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 bg-primary/10 text-primary rounded text-xs">
                        {node.type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {editingNode === node.id ? (
                        <textarea
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                          className="w-full px-2 py-1 bg-background border rounded text-sm min-h-[60px] resize-y"
                        />
                      ) : (
                        <div className="max-h-28 overflow-auto text-muted-foreground">
                          <RichTextContent content={node.content || "-"} />
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {editingNode === node.id ? (
                          <button
                            onClick={() => handleSave(node.id)}
                            className="p-1.5 text-green-600 hover:bg-green-100 rounded"
                            title="保存"
                          >
                            <Save size={14} />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleEdit(node.id, node.content || "")}
                            className="p-1.5 text-muted-foreground hover:bg-muted rounded"
                            title="编辑"
                          >
                            <Edit3 size={14} />
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(node.id)}
                          className="p-1.5 text-destructive hover:bg-destructive/10 rounded"
                          title="删除"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-card border rounded-xl p-4">
      <p className="text-sm text-muted-foreground mb-1">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  )
}
