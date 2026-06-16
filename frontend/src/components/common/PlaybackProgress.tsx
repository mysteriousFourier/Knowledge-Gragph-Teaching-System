import { Activity, CheckCircle2, Clock3, Database, Loader2, Timer } from "lucide-react"
import type { AudioPlaybackPosition, PlaybackProgress as PlaybackProgressState } from "@/hooks/useLecturePlayback"
import { cn } from "@/lib/utils"

export function PlaybackProgress({
  progress,
  statusText,
  audioPosition,
  onSeek,
}: {
  progress: PlaybackProgressState
  statusText: string
  audioPosition?: AudioPlaybackPosition
  onSeek?: (percent: number) => void
}) {
  const showBar = progress.total > 1 || progress.isActive
  const displayPercent = progress.total > 0 ? Math.max(progress.percent, progress.isActive ? 6 : 0) : 0
  const canSeek = Boolean(audioPosition?.seekable && onSeek)

  return (
    <div className="border-b px-4 py-2.5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          {progress.isActive ? (
            <Loader2 size={15} className="shrink-0 animate-spin text-primary" />
          ) : (
            <Activity size={15} className="shrink-0 text-muted-foreground" />
          )}
          <span className="min-w-0 truncate text-muted-foreground">{statusText}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Activity size={13} />
            {progress.providerLabel}
          </span>
          {progress.total > 0 && (
            <span className="inline-flex items-center gap-1">
              <CheckCircle2 size={13} />
              就绪 {progress.ready}/{progress.total}
            </span>
          )}
          {progress.pending > 0 && (
            <span className="inline-flex items-center gap-1">
              <Clock3 size={13} />
              生成中 {progress.pending}
            </span>
          )}
          {progress.cacheHits > 0 && (
            <span className="inline-flex items-center gap-1">
              <Database size={13} />
              缓存 {progress.cacheHits}
            </span>
          )}
        </div>
      </div>
      {showBar && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full bg-primary transition-all duration-500",
              progress.isActive && progress.ready === 0 && "animate-pulse"
            )}
            style={{ width: `${displayPercent}%` }}
          />
        </div>
      )}
      <div className="mt-3 grid gap-2 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center">
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <Timer size={13} />
          {formatPlaybackTime(audioPosition?.currentTime || 0)}
        </span>
        <input
          type="range"
          min={0}
          max={100}
          step={0.1}
          value={audioPosition?.percent || 0}
          disabled={!canSeek}
          aria-label="语音播放进度"
          onChange={(event) => onSeek?.(Number(event.target.value))}
          className={cn(
            "h-2 w-full cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-45",
            canSeek && "focus:outline-none focus:ring-2 focus:ring-primary/20"
          )}
        />
        <span className="text-xs text-muted-foreground sm:text-right">
          {audioPosition?.duration ? formatPlaybackTime(audioPosition.duration) : "--:--"}
        </span>
      </div>
    </div>
  )
}

function formatPlaybackTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "00:00"
  const totalSeconds = Math.floor(seconds)
  const minutes = Math.floor(totalSeconds / 60)
  const remainingSeconds = totalSeconds % 60
  return `${minutes.toString().padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`
}
