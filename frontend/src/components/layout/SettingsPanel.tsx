import { useEffect, useState } from "react"
import { Eye, EyeOff, Save, X } from "lucide-react"
import { useConfigStatus, useSaveConfig } from "@/api/education"
import { useAppDispatch, useAppSelector } from "@/store/hooks"
import { setSettingsOpen } from "@/store/slices/uiSlice"

const DEFAULT_GPT_BASE = "https://api.openai.com/v1"
const DEFAULT_GPT_MODEL = "gpt-5.5"

export function SettingsPanel() {
  const dispatch = useAppDispatch()
  const open = useAppSelector((state) => state.ui.settingsOpen)
  const { data, refetch } = useConfigStatus()
  const saveConfig = useSaveConfig()
  const [apiKey, setApiKey] = useState("")
  const [apiBase, setApiBase] = useState(DEFAULT_GPT_BASE)
  const [model, setModel] = useState(DEFAULT_GPT_MODEL)
  const [showKey, setShowKey] = useState(false)
  const [message, setMessage] = useState("")
  const [savedConfigured, setSavedConfigured] = useState<boolean | null>(null)

  useEffect(() => {
    if (!data) return
    setApiBase(data.gpt_api_base || DEFAULT_GPT_BASE)
    setModel(data.gpt_model || data.pro_model || DEFAULT_GPT_MODEL)
    setSavedConfigured(data.gpt_api_key_configured ?? false)
  }, [data])

  if (!open) return null

  const apiKeyConfigured = savedConfigured ?? data?.gpt_api_key_configured ?? false

  const handleSave = async () => {
    setMessage("")
    try {
      const result = await saveConfig.mutateAsync({
        gpt_api_key: apiKey.trim() || undefined,
        gpt_api_base: apiBase.trim() || undefined,
        gpt_model: model.trim() || undefined,
      })
      setApiKey("")
      setSavedConfigured(result.gpt_api_key_configured ?? false)
      setApiBase(result.gpt_api_base || apiBase)
      setModel(result.gpt_model || result.pro_model || model)
      setMessage((result.gpt_api_key_configured ?? false) ? "配置已保存，GPT 5.5 API Key 已连接。" : "配置已保存，但 GPT API Key 仍为空。")
      await refetch()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "后端配置接口不可用"
      setMessage(`保存失败：${errorMessage}。请确认服务已按当前代码重新启动。`)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/35" onMouseDown={() => dispatch(setSettingsOpen(false))}>
      <aside
        className="absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l bg-background p-5 shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">设置</h2>
            <p className="text-sm text-muted-foreground">GPT 5.5 API 用于授课文案、题库、问答和 LaTeX PPT 生成。</p>
          </div>
          <button
            type="button"
            onClick={() => dispatch(setSettingsOpen(false))}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border hover:bg-accent"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4">
          <div className="rounded-lg border bg-card p-3 text-sm">
            <div className="font-medium">当前状态</div>
            <div className="mt-2 text-muted-foreground">API Key：{apiKeyConfigured ? "已配置" : "未配置"}</div>
            <div className="text-muted-foreground">API Base：{apiBase || "-"}</div>
            <div className="text-muted-foreground">默认模型：{model || "-"}</div>
          </div>

          <label className="block text-sm font-medium">
            GPT API Key
            <div className="mt-1 flex rounded-lg border bg-background">
              <input
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                type={showKey ? "text" : "password"}
                placeholder={apiKeyConfigured ? "留空则保留现有 Key" : "请输入 GPT API Key"}
                className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm outline-none"
              />
              <button
                type="button"
                onClick={() => setShowKey((value) => !value)}
                className="px-3 text-muted-foreground hover:text-foreground"
              >
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </label>

          <label className="block text-sm font-medium">
            GPT API Base URL
            <input
              value={apiBase}
              onChange={(event) => setApiBase(event.target.value)}
              className="mt-1 w-full rounded-lg border bg-background px-3 py-2.5 text-sm outline-none focus:border-primary"
            />
          </label>

          <label className="block text-sm font-medium">
            GPT 模型
            <input
              value={model}
              onChange={(event) => setModel(event.target.value)}
              className="mt-1 w-full rounded-lg border bg-background px-3 py-2.5 text-sm outline-none focus:border-primary"
            />
          </label>

          <button
            type="button"
            onClick={handleSave}
            disabled={saveConfig.isPending}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            <Save size={16} />
            {saveConfig.isPending ? "保存中..." : "保存设置"}
          </button>

          {message && <div className="rounded-lg border bg-card p-3 text-sm text-muted-foreground">{message}</div>}

          <div className="rounded-lg bg-muted p-3 text-xs leading-6 text-muted-foreground">
            保存后会写入项目根目录的 .env 文件，并同步到当前后端进程；后续大模型调用默认使用 GPT 5.5。
          </div>
        </div>
      </aside>
    </div>
  )
}
