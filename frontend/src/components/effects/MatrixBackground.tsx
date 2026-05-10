import { useEffect, useRef } from "react"

export function MatrixBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d", { alpha: false })
    if (!ctx) return

    const glyphRamp = [
      [" ", ".", "`", "."],
      [".", ":", "·", "'"],
      [":", ";", "-", ","],
      ["-", "=", "~", "_"],
      ["+", "*", "x", "<", ">"],
      ["#", "%", "&", "$"],
      ["@", "M", "W", "8"],
    ]

    let width = 0
    let height = 0
    let ratio = 1
    let fontSize = 16
    let cellW = 14
    let cellH = 18
    let columns = 0
    let rows = 0
    let cells: Array<{
      x: number
      y: number
      seed: number
      phase: number
      grain: number
    }> = []
    let pulses: Array<{
      x: number
      y: number
      startedAt: number
      strength: number
      shift: number
      phase: number
    }> = []
    let charShift = 0
    let fieldCharge = 0
    let lastClickAt = 0
    let lastFrame = 0
    const startedAt = performance.now()
    const pointer = {
      x: 0,
      y: 0,
      active: false,
      lastMoveAt: 0,
    }

    function resizeCanvas() {
      ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = window.innerWidth
      height = window.innerHeight
      fontSize = width < 700 ? 12 : 15
      cellW = width < 700 ? 12 : 14
      cellH = width < 700 ? 17 : 19
      canvas!.width = Math.floor(width * ratio)
      canvas!.height = Math.floor(height * ratio)
      canvas!.style.width = `${width}px`
      canvas!.style.height = `${height}px`
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0)
      columns = Math.ceil(width / cellW) + 2
      rows = Math.ceil(height / cellH) + 2
      cells = []

      for (let row = 0; row < rows; row += 1) {
        for (let col = 0; col < columns; col += 1) {
          cells.push({
            x: col * cellW - cellW,
            y: row * cellH - cellH,
            seed: Math.floor(Math.random() * 10000),
            phase: Math.random() * Math.PI * 2,
            grain: Math.random(),
          })
        }
      }
    }

    function draw(timestamp: number) {
      if (timestamp - lastFrame < 36) {
        requestAnimationFrame(draw)
        return
      }
      lastFrame = timestamp

      const now = performance.now()
      const elapsed = now - startedAt
      const idleMs = now - lastClickAt
      const hoverFade = pointer.active
        ? Math.max(0, 1 - (now - pointer.lastMoveAt) / 1250)
        : 0
      const maxRadius = width < 700 ? 260 : 430
      const breath = 0.5 + Math.sin(elapsed * 0.00125) * 0.5
      const slowBreath = 0.5 + Math.sin(elapsed * 0.00038 + 1.4) * 0.5

      if (lastClickAt && idleMs > 1400) {
        fieldCharge *= 0.965
        if (fieldCharge < 0.004) {
          fieldCharge = 0
        }
      }

      ctx!.fillStyle = "#000000"
      ctx!.fillRect(0, 0, width, height)
      ctx!.font = `${fontSize}px "JetBrains Mono", Consolas, monospace`
      ctx!.textBaseline = "top"
      ctx!.textAlign = "left"

      const livePulses = []
      for (const pulse of pulses) {
        if (now - pulse.startedAt < 5200) {
          livePulses.push(pulse)
        }
      }
      pulses = livePulses

      for (const cell of cells) {
        const idleFlow =
          0.5 +
          Math.sin(
            cell.x * 0.011 + cell.y * 0.016 - elapsed * 0.00145 + cell.phase
          ) *
            0.5
        const grainBreath =
          0.5 +
          Math.sin(elapsed * 0.001 + cell.phase + cell.seed * 0.011) * 0.5
        let brightness =
          0.012 +
          cell.grain * 0.016 +
          idleFlow * (0.018 + breath * 0.026) +
          grainBreath * (0.01 + slowBreath * 0.014) +
          fieldCharge * 0.025
        let localShift = 0

        if (hoverFade > 0) {
          const dx = cell.x - pointer.x
          const dy = cell.y - pointer.y
          const distance = Math.hypot(dx, dy)
          const ripple =
            (Math.sin(distance * 0.062 - elapsed * 0.006 + cell.phase) + 1) *
            0.5
          const falloff = Math.exp(-distance / (width < 700 ? 145 : 230))
          brightness += ripple * falloff * 0.18 * hoverFade
        }

        let waveSum = 0
        let waveEnergy = 0
        let overlapA = 0
        let overlapB = 0
        let overlapPhaseA = 0
        let overlapPhaseB = 0

        for (const pulse of pulses) {
          const age = now - pulse.startedAt
          const progress = Math.min(1, age / 3000)
          const radius = Math.min(maxRadius, 26 + progress * maxRadius)
          const dx = cell.x - pulse.x
          const dy = cell.y - pulse.y
          const distance = Math.hypot(dx, dy)
          const ringWidth = 26 + radius * 0.08
          const ring = Math.exp(
            -Math.pow(distance - radius, 2) / (2 * ringWidth * ringWidth)
          )
          const interior =
            distance < radius
              ? Math.max(0, 1 - distance / Math.max(radius, 1))
              : 0
          const decay = Math.max(0, 1 - age / 5200)
          const phase = distance * 0.118 - age * 0.013 + pulse.phase
          const wave = Math.sin(phase) * ring * decay * pulse.strength
          const energy = Math.abs(wave)

          waveSum += wave
          waveEnergy += energy
          brightness += interior * 0.08 * decay * pulse.strength

          if (energy > overlapA) {
            overlapB = overlapA
            overlapPhaseB = overlapPhaseA
            overlapA = energy
            overlapPhaseA = phase
          } else if (energy > overlapB) {
            overlapB = energy
            overlapPhaseB = phase
          }

          if (ring > 0.1 || interior > 0.2) {
            localShift += pulse.shift
          }
        }

        if (pulses.length > 0) {
          const constructive = Math.abs(waveSum)
          const destructive = Math.max(0, waveEnergy - constructive)
          brightness +=
            Math.max(0, constructive * 0.42 - destructive * 0.075)
          brightness += Math.min(0.18, waveEnergy * 0.07)

          if (overlapB > 0.05) {
            const beat =
              0.5 +
              Math.sin(
                overlapPhaseA -
                  overlapPhaseB +
                  cell.x * 0.044 -
                  cell.y * 0.027
              ) *
                0.5
            brightness +=
              beat * Math.min(0.24, overlapA * overlapB * 1.05)
            localShift += Math.floor((beat + overlapA + overlapB) * 13)
          }
        }

        brightness = Math.min(0.92, brightness)
        if (brightness < 0.012) {
          continue
        }

        const level = Math.max(
          0,
          Math.min(glyphRamp.length - 1, Math.floor(brightness * 8))
        )
        const options = glyphRamp[level]
        const stagger = 260 + (cell.seed % 210)
        const breathTick = Math.floor(
          (elapsed + cell.phase * 900) / stagger
        )
        const glyph =
          options[
            (cell.seed + breathTick + charShift + localShift) %
              options.length
          ]
        const alpha = Math.min(0.86, 0.025 + brightness * 0.82)
        const cool = localShift > 0 && brightness > 0.22

        ctx!.fillStyle = cool
          ? `rgba(220, 246, 255, ${alpha})`
          : `rgba(238, 238, 238, ${alpha})`
        ctx!.fillText(glyph, cell.x, cell.y)
      }

      requestAnimationFrame(draw)
    }

    function updatePointer(event: PointerEvent) {
      pointer.x = event.clientX
      pointer.y = event.clientY
      pointer.active = true
      pointer.lastMoveAt = performance.now()
    }

    function triggerPulse(event: PointerEvent) {
      updatePointer(event)
      const now = performance.now()
      fieldCharge = Math.min(0.72, fieldCharge + 0.14)
      charShift = (charShift + 5 + Math.floor(Math.random() * 9)) % 997
      lastClickAt = now
      pulses.push({
        x: event.clientX,
        y: event.clientY,
        startedAt: now,
        strength: Math.min(1.35, 1 + pulses.length * 0.08),
        shift: charShift,
        phase: Math.random() * Math.PI * 2,
      })
      pulses = pulses.slice(-8)
    }

    window.addEventListener("resize", resizeCanvas, { passive: true })
    window.addEventListener("pointermove", updatePointer, { passive: true })
    window.addEventListener("pointerdown", triggerPulse, { passive: true })
    window.addEventListener("pointerleave", () => {
      pointer.active = false
    })

    resizeCanvas()
    requestAnimationFrame(draw)

    return () => {
      window.removeEventListener("resize", resizeCanvas)
      window.removeEventListener("pointermove", updatePointer)
      window.removeEventListener("pointerdown", triggerPulse)
      window.removeEventListener("pointerleave", () => {
        pointer.active = false
      })
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 w-full h-full"
      style={{ zIndex: 0 }}
      aria-hidden="true"
    />
  )
}
