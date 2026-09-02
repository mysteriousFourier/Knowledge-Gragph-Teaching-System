import { MarkdownRenderer } from "./MarkdownRenderer"

interface RichTextContentProps {
  content: string
  inline?: boolean
  className?: string
}

export function RichTextContent({ content, inline = false, className = "" }: RichTextContentProps) {
  if (!content) {
    return <span className="text-muted-foreground italic">暂无内容</span>
  }

  if (inline) {
    return <MarkdownRenderer content={content.trim()} className={className} inline />
  }

  return <MarkdownRenderer content={content} className={className} />
}
