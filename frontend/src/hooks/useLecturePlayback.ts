import { useMemo, useState } from "react"

export const ttsProvider = "none" as const

interface UseLecturePlaybackOptions {
  segmentCount: number
  initialSegment?: number
}

export function useLecturePlayback({ segmentCount, initialSegment = 0 }: UseLecturePlaybackOptions) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentSegment, setCurrentSegmentState] = useState(initialSegment)

  const hasSegments = segmentCount > 0
  const providerLabel = ttsProvider === "none" ? "语音接口未接入" : "语音播放可用"

  const setCurrentSegment = (next: number | ((current: number) => number)) => {
    setCurrentSegmentState((current) => {
      const value = typeof next === "function" ? next(current) : next
      return Math.min(Math.max(value, 0), Math.max(segmentCount - 1, 0))
    })
  }

  const play = () => {
    if (!hasSegments) return
    setIsPlaying(true)
    // TODO: when a real TTS provider is configured, request audio for currentSegment here.
  }

  const pause = () => {
    setIsPlaying(false)
    // TODO: pause or stop the active provider playback instance here.
  }

  const toggle = () => {
    if (isPlaying) {
      pause()
    } else {
      play()
    }
  }

  const reset = (segment = 0) => {
    setIsPlaying(false)
    setCurrentSegmentState(Math.min(Math.max(segment, 0), Math.max(segmentCount - 1, 0)))
  }

  const statusText = useMemo(() => {
    if (!hasSegments) return "暂无可播放内容"
    if (ttsProvider === "none") return isPlaying ? "播放状态已开启，语音接口未接入" : "语音接口未接入"
    return isPlaying ? "播放中" : "已暂停"
  }, [hasSegments, isPlaying])

  return {
    currentSegment,
    hasSegments,
    isPlaying,
    pause,
    play,
    provider: ttsProvider,
    providerLabel,
    reset,
    setCurrentSegment,
    statusText,
    toggle,
  }
}
