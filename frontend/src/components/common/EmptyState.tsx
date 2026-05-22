import { FileQuestion } from "lucide-react"

interface EmptyStateProps {
  title?: string
  description?: string
  icon?: React.ReactNode
  action?: React.ReactNode
}

export function EmptyState({
  title = "暂无数据",
  description = "当前没有可显示的内容",
  icon,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="mb-4 text-muted-foreground">
        {icon || <FileQuestion size={48} strokeWidth={1.5} />}
      </div>
      <h3 className="text-lg font-medium text-foreground mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-sm mb-4">{description}</p>
      {action}
    </div>
  )
}
