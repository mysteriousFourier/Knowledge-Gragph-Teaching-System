(function () {
    const canvas = document.getElementById("workspace-ambient-canvas");
    if (!canvas) {
        return;
    }

    const ctx = canvas.getContext("2d", { alpha: true });
    const glyphRamp = [
        [" ", ".", "`"],
        [".", ":", "路"],
        [":", ";", "-", ","],
        ["-", "=", "~", "_"],
        ["+", "*", "x", "<", ">"],
        ["#", "%", "&"],
        ["@", "W", "8"]
    ];

    let width = 0;
    let height = 0;
    let ratio = 1;
    let fontSize = 13;
    let cellW = 14;
    let cellH = 20;
    let columns = 0;
    let rows = 0;
    let cells = [];
    let pulses = [];
    let charShift = 0;
    let fieldCharge = 0;
    let lastClickAt = 0;
    let lastFrame = 0;
    const startedAt = performance.now();
    const prefersReducedMotion = window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let pageVisible = document.visibilityState !== "hidden";
    const pointer = {
        x: 0,
        y: 0,
        active: false,
        lastMoveAt: 0
    };

    function resizeCanvas() {
        ratio = Math.min(window.devicePixelRatio || 1, prefersReducedMotion ? 1 : 1.5);
        width = window.innerWidth;
        height = window.innerHeight;
        fontSize = width < 700 ? 11 : 13;
        cellW = width < 700 ? 13 : 15;
        cellH = width < 700 ? 18 : 21;
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        columns = Math.ceil(width / cellW) + 2;
        rows = Math.ceil(height / cellH) + 2;
        cells = [];

        for (let row = 0; row < rows; row += 1) {
            for (let col = 0; col < columns; col += 1) {
                cells.push({
                    x: col * cellW - cellW,
                    y: row * cellH - cellH,
                    seed: Math.floor(Math.random() * 12000),
                    phase: Math.random() * Math.PI * 2,
                    grain: Math.random()
                });
            }
        }
    }

    function draw(timestamp) {
        if (!pageVisible) {
            requestAnimationFrame(draw);
            return;
        }

        const hasActiveWave = pulses.length > 0 ||
            fieldCharge > 0.012 ||
            (pointer.active && timestamp - pointer.lastMoveAt < 1200);
        const frameInterval = prefersReducedMotion ? 140 : (hasActiveWave ? 52 : 84);
        if (timestamp - lastFrame < frameInterval) {
            requestAnimationFrame(draw);
            return;
        }
        lastFrame = timestamp;

        const now = performance.now();
        const elapsed = now - startedAt;
        const idleMs = now - lastClickAt;
        const hoverFade = pointer.active ? Math.max(0, 1 - (now - pointer.lastMoveAt) / 1150) : 0;
        const maxRadius = width < 700 ? 230 : 360;
        const breath = 0.5 + Math.sin(elapsed * 0.00135) * 0.5;
        const slowBreath = 0.5 + Math.sin(elapsed * 0.00042 + 1.7) * 0.5;

        if (lastClickAt && idleMs > 1300) {
            fieldCharge *= 0.955;
            if (fieldCharge < 0.003) {
                fieldCharge = 0;
            }
        }

        ctx.clearRect(0, 0, width, height);
        ctx.font = `${fontSize}px "JetBrains Mono", Consolas, monospace`;
        ctx.textBaseline = "top";
        ctx.textAlign = "left";

        pulses = pulses.filter((pulse) => now - pulse.startedAt < 4200);

        for (const cell of cells) {
            const idleFlow = 0.5 + Math.sin(cell.x * 0.012 + cell.y * 0.017 - elapsed * 0.0016 + cell.phase) * 0.5;
            const grainBreath = 0.5 + Math.sin(elapsed * 0.0011 + cell.phase + cell.seed * 0.013) * 0.5;
            let brightness = 0.012
                + cell.grain * 0.012
                + idleFlow * (0.014 + breath * 0.018)
                + grainBreath * (0.008 + slowBreath * 0.01)
                + fieldCharge * 0.016;
            let localShift = 0;

            if (hoverFade > 0) {
                const dx = cell.x - pointer.x;
                const dy = cell.y - pointer.y;
                const distance = Math.hypot(dx, dy);
                const ripple = (Math.sin(distance * 0.07 - elapsed * 0.007 + cell.phase) + 1) * 0.5;
                const falloff = Math.exp(-distance / (width < 700 ? 110 : 170));
                brightness += ripple * falloff * 0.12 * hoverFade;
            }

            let waveSum = 0;
            let waveEnergy = 0;
            let overlapA = 0;
            let overlapB = 0;
            let overlapPhaseA = 0;
            let overlapPhaseB = 0;

            for (const pulse of pulses) {
                const age = now - pulse.startedAt;
                const progress = Math.min(1, age / 2450);
                const radius = Math.min(maxRadius, 20 + progress * maxRadius);
                const dx = cell.x - pulse.x;
                const dy = cell.y - pulse.y;
                const distance = Math.hypot(dx, dy);
                const ringWidth = 18 + radius * 0.068;
                const ring = Math.exp(-Math.pow(distance - radius, 2) / (2 * ringWidth * ringWidth));
                const interior = distance < radius ? Math.max(0, 1 - distance / Math.max(radius, 1)) : 0;
                const decay = Math.max(0, 1 - age / 4200);
                const phase = distance * 0.135 - age * 0.015 + pulse.phase;
                const wave = Math.sin(phase) * ring * decay * pulse.strength;
                const energy = Math.abs(wave);

                waveSum += wave;
                waveEnergy += energy;
                brightness += interior * 0.045 * decay * pulse.strength;

                if (energy > overlapA) {
                    overlapB = overlapA;
                    overlapPhaseB = overlapPhaseA;
                    overlapA = energy;
                    overlapPhaseA = phase;
                } else if (energy > overlapB) {
                    overlapB = energy;
                    overlapPhaseB = phase;
                }

                if (ring > 0.1 || interior > 0.2) {
                    localShift += pulse.shift;
                }
            }

            if (pulses.length > 0) {
                const constructive = Math.abs(waveSum);
                const destructive = Math.max(0, waveEnergy - constructive);
                const interference = Math.max(0, constructive * 0.32 - destructive * 0.055);
                brightness += interference + Math.min(0.12, waveEnergy * 0.055);

                if (overlapB > 0.045) {
                    const beat = 0.5 + Math.sin(overlapPhaseA - overlapPhaseB + cell.x * 0.048 - cell.y * 0.031) * 0.5;
                    brightness += beat * Math.min(0.18, overlapA * overlapB * 0.9);
                    localShift += Math.floor((beat + overlapA + overlapB) * 11);
                }
            }

            brightness = Math.min(0.68, brightness);
            if (brightness < 0.01) {
                continue;
            }

            const level = Math.max(0, Math.min(glyphRamp.length - 1, Math.floor(brightness * 9)));
            const options = glyphRamp[level];
            const stagger = 280 + (cell.seed % 260);
            const breathTick = Math.floor((elapsed + cell.phase * 800) / stagger);
            const glyph = options[(cell.seed + breathTick + charShift + localShift) % options.length];
            const alpha = Math.min(0.68, 0.025 + brightness * 0.78);
            const cool = localShift > 0 && brightness > 0.14;

            ctx.fillStyle = cool
                ? `rgba(218, 246, 255, ${alpha})`
                : `rgba(236, 240, 245, ${alpha})`;
            ctx.fillText(glyph, cell.x, cell.y);
        }

        requestAnimationFrame(draw);
    }

    function updatePointer(event) {
        pointer.x = event.clientX;
        pointer.y = event.clientY;
        pointer.active = true;
        pointer.lastMoveAt = performance.now();
    }

    function triggerPulse(event) {
        updatePointer(event);
        const now = performance.now();
        const target = event.target instanceof Element ? event.target : null;
        const isContentClick = Boolean(target && target.closest(
            ".panel, .panel-section, .header, .float-window, .modal, .lecture-editor-wrapper, .course-content-wrapper, .knowledge-graph-panel, .lecture-text-panel"
        ));
        fieldCharge = Math.min(0.42, fieldCharge + (isContentClick ? 0.04 : 0.1));
        charShift = (charShift + 3 + Math.floor(Math.random() * 7)) % 997;
        lastClickAt = now;
        pulses.push({
            x: event.clientX,
            y: event.clientY,
            startedAt: now,
            strength: isContentClick ? 0.5 : 0.96,
            shift: charShift,
            phase: Math.random() * Math.PI * 2
        });
        pulses = pulses.slice(-5);
    }

    window.addEventListener("resize", resizeCanvas, { passive: true });
    window.addEventListener("pointermove", updatePointer, { passive: true });
    window.addEventListener("pointerdown", triggerPulse, { passive: true });
    window.addEventListener("pointerleave", () => {
        pointer.active = false;
    });
    document.addEventListener("visibilitychange", () => {
        pageVisible = document.visibilityState !== "hidden";
    });

    resizeCanvas();
    requestAnimationFrame(draw);
})();
