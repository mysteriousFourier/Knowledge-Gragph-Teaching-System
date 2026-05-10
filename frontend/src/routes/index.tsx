import { createFileRoute, Link } from "@tanstack/react-router"
import { BookOpen, FileUp, GraduationCap, LogIn, Network, ShieldCheck } from "lucide-react"

export const Route = createFileRoute("/")({
  component: HomePage,
})

function HomePage() {
  return (
    <section>
      <span className="sheet-label">System Index</span>
      <h1 className="mt-3 text-4xl font-bold">知识图谱教学系统</h1>
      <p className="mt-5 leading-8 text-muted-foreground">
        右侧纸面是实际工作入口，左侧图谱画布保持课程上下文。登录、教师端、学生端、知识图谱和图谱管理都在同一套界面骨架内展开。
      </p>

      <div className="route-grid">
        <RouteCard to="/login" icon={<LogIn size={20} />} title="登录" text="学生 / 教师身份选择" />
        <RouteCard to="/teacher" icon={<BookOpen size={20} />} title="教师端" text="备课、PPT、授课、题库" />
        <RouteCard to="/student" icon={<GraduationCap size={20} />} title="学生端" text="学习、练习、复习" />
        <RouteCard to="/graph" icon={<Network size={20} />} title="知识图谱" text="浏览、筛选、邻居聚焦" />
        <RouteCard to="/graph/admin" icon={<ShieldCheck size={20} />} title="图谱管理" text="新增、编辑、删除节点" />
      </div>

      <div className="mt-8 grid gap-3 border-t pt-6">
        <WorkflowLine icon={<BookOpen size={17} />} title="Prepare" text="导入章节和图谱，生成授课文案。" />
        <WorkflowLine icon={<FileUp size={17} />} title="PPT" text="解析幻灯片，生成逐页讲稿。" />
        <WorkflowLine icon={<GraduationCap size={17} />} title="Learn" text="学生阅读章节内容并围绕当前材料提问。" />
      </div>
    </section>
  )
}

function RouteCard({ to, icon, title, text }: { to: string; icon: React.ReactNode; title: string; text: string }) {
  return (
    <Link to={to} className="block bg-muted p-4 text-left no-underline">
      <div className="mb-4 text-primary">{icon}</div>
      <strong className="block text-lg">{title}</strong>
      <small className="mt-2 block leading-6 text-muted-foreground">{text}</small>
    </Link>
  )
}

function WorkflowLine({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="grid grid-cols-[auto_1fr] gap-3 border-b pb-3">
      <div className="text-primary">{icon}</div>
      <div>
        <div className="font-mono text-xs uppercase text-primary">{title}</div>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{text}</p>
      </div>
    </div>
  )
}
