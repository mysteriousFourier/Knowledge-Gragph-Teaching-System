import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import rehypeRaw from "rehype-raw"
import "katex/dist/katex.min.css"

interface MarkdownRendererProps {
  content: string
  className?: string
  inline?: boolean
}

function normalizeLatexDelimiters(content: string) {
  return content
    .split(/(```[\s\S]*?```)/g)
    .map((block) => {
      if (block.startsWith("```")) return block
      return block
        .split(/(`[^`\n]*`)/g)
        .map((segment) => {
          if (segment.startsWith("`")) return segment
          return normalizeBrokenDisplayMath(wrapBareLatexEnvironments(segment))
            .replace(/\\\[([\s\S]*?)\\\]/g, "\n\n$$\n$1\n$$\n\n")
            .replace(/\\\(([\s\S]*?)\\\)/g, "$$$1$")
        })
        .join("")
    })
    .join("")
}

function normalizeBrokenDisplayMath(segment: string) {
  return segment
    .replace(/\\\\\[/g, "\\[")
    .replace(/\\\\\]/g, "\\]")
    .replace(/(^|\n)[ \t]*\\\[[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*\\\][ \t]*(?=\n|$)/g, (_match, prefix, formula) => {
      return `${prefix}\n\n$$\n${String(formula).trim()}\n$$\n\n`
    })
    .replace(/\\\[\s*\\\]\s*((?:\\begin\{[\s\S]*?\\end\{[^}]+\}|[^\n][\s\S]*?))(?:\n{2,}|$)/g, (_match, formula) => {
      return `\n\n$$\n${String(formula).trim()}\n$$\n\n`
    })
}

function wrapBareLatexEnvironments(segment: string) {
  const mathEnvironments = "array|aligned|align|gather|matrix|pmatrix|bmatrix|vmatrix|Vmatrix|cases|equation|split"
  const pattern = new RegExp(String.raw`\\begin\{(${mathEnvironments})\}[\s\S]*?\\end\{\1\}`, "g")

  return segment.replace(pattern, (match, _env, offset, fullText) => {
    if (isInsideMathBlock(fullText, offset)) return match
    return `\n\n$$\n${match}\n$$\n\n`
  })
}

function isInsideMathBlock(text: string, offset: number) {
  const before = text.slice(0, offset)
  const dollarBlockCount = before.split("$$").length - 1
  const lastBracketStart = before.lastIndexOf("\\[")
  const lastBracketEnd = before.lastIndexOf("\\]")
  return dollarBlockCount % 2 === 1 || lastBracketStart > lastBracketEnd
}

export function MarkdownRenderer({ content, className = "", inline = false }: MarkdownRendererProps) {
  const normalizedContent = normalizeLatexDelimiters(content)
  const components = {
    pre: ({ children }: { children?: React.ReactNode }) => (
      <pre className="bg-muted p-3 rounded-lg overflow-x-auto">{children}</pre>
    ),
    code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
      const isInline = !className
      return isInline ? (
        <code className="bg-muted px-1.5 py-0.5 rounded text-sm">{children}</code>
      ) : (
        <code className={className}>{children}</code>
      )
    },
    ...(inline ? { p: ({ children }: { children?: React.ReactNode }) => <>{children}</> } : {}),
  }

  if (inline) {
    return (
      <span className={`inline whitespace-normal ${className}`}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeKatex, rehypeRaw]}
          components={components}
        >
          {normalizedContent}
        </ReactMarkdown>
      </span>
    )
  }

  return (
    <div className={`prose prose-sm max-w-none dark:prose-invert ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeRaw]}
        components={components}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  )
}
