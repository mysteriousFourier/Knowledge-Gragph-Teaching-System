import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/teacher/ppt")({
  component: TeacherPptPage,
})

function TeacherPptPage() {
  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  return (
    <div className="relative space-y-8">
      <PptIndex onJump={scrollToSection} />

      <section id="ppt-generate" className="scroll-mt-6 rounded-xl border bg-card">
        <div className="border-b p-4">
          <h1 className="text-2xl font-bold">PPT 生成</h1>
        </div>
        <div className="overflow-hidden">
          <iframe
            title="LaTeX Beamer 生成器"
            src="/beamer-generator/index.html?v=20260527-min-pages-figpath-v75"
            className="h-[calc(100dvh-120px)] min-h-[760px] w-full border-0"
          />
        </div>
      </section>

      <section id="ppt-display" className="scroll-mt-6 rounded-xl border bg-card">
        <div className="border-b p-4">
          <h1 className="text-2xl font-bold">PPT 展示</h1>
        </div>
        <div className="overflow-hidden">
          <iframe
            title="导入 LaTeX 生成可编辑 PPT"
            src="/beamer-generator/index.html?mode=latex-import&v=20260527-min-pages-figpath-v75"
            className="h-[calc(100dvh-120px)] min-h-[760px] w-full border-0"
          />
        </div>
      </section>
    </div>
  )
}

function PptIndex({ onJump }: { onJump: (id: string) => void }) {
  return (
    <div className="ppt-section-index">
      <button type="button" className="ppt-section-index-trigger" aria-label="PPT 索引">
        &lt;&lt;
      </button>
      <div className="ppt-section-index-menu">
        <button type="button" onClick={() => onJump("ppt-generate")} className="ppt-section-index-item">
          PPT 生成
        </button>
        <button type="button" onClick={() => onJump("ppt-display")} className="ppt-section-index-item">
          PPT 展示
        </button>
      </div>
    </div>
  )
}
