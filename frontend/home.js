(function () {
    document.documentElement.dataset.homeMotionVersion = "13";

    const canvas = document.getElementById("matrix-canvas");
    if (!canvas) {
        return;
    }

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) {
        return;
    }
    const glyphRamp = [
        [" ", ".", "`", "."],
        [".", ":", "·", "'"],
        [":", ";", "-", ","],
        ["-", "=", "~", "_"],
        ["+", "*", "x", "<", ">"],
        ["#", "%", "&", "$"],
        ["@", "M", "W", "8"]
    ];
    let width = 0;
    let height = 0;
    let ratio = 1;
    let fontSize = 16;
    let cellW = 14;
    let cellH = 18;
    let columns = 0;
    let rows = 0;
    let cells = [];
    let pulses = [];
    let charShift = 0;
    let fieldCharge = 0;
    let lastClickAt = 0;
    let lastFrame = 0;
    const startedAt = performance.now();
    const pointer = {
        x: 0,
        y: 0,
        active: false,
        lastMoveAt: 0
    };

    function resizeCanvas() {
        ratio = Math.min(window.devicePixelRatio || 1, 2);
        width = window.innerWidth;
        height = window.innerHeight;
        fontSize = width < 700 ? 12 : 15;
        cellW = width < 700 ? 12 : 14;
        cellH = width < 700 ? 17 : 19;
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
                    seed: Math.floor(Math.random() * 10000),
                    phase: Math.random() * Math.PI * 2,
                    grain: Math.random()
                });
            }
        }
    }

    function draw(timestamp) {
        if (timestamp - lastFrame < 36) {
            requestAnimationFrame(draw);
            return;
        }
        lastFrame = timestamp;

        const now = performance.now();
        const elapsed = now - startedAt;
        const idleMs = now - lastClickAt;
        const hoverFade = pointer.active ? Math.max(0, 1 - (now - pointer.lastMoveAt) / 1250) : 0;
        const maxRadius = width < 700 ? 260 : 430;
        const breath = 0.5 + Math.sin(elapsed * 0.00125) * 0.5;
        const slowBreath = 0.5 + Math.sin(elapsed * 0.00038 + 1.4) * 0.5;

        if (lastClickAt && idleMs > 1400) {
            fieldCharge *= 0.965;
            if (fieldCharge < 0.004) {
                fieldCharge = 0;
            }
        }

        ctx.fillStyle = "#000000";
        ctx.fillRect(0, 0, width, height);
        ctx.font = `${fontSize}px "JetBrains Mono", Consolas, monospace`;
        ctx.textBaseline = "top";
        ctx.textAlign = "left";

        const livePulses = [];
        for (const pulse of pulses) {
            if (now - pulse.startedAt < 5200) {
                livePulses.push(pulse);
            }
        }
        pulses = livePulses;

        for (const cell of cells) {
            const idleFlow = 0.5 + Math.sin(cell.x * 0.011 + cell.y * 0.016 - elapsed * 0.00145 + cell.phase) * 0.5;
            const grainBreath = 0.5 + Math.sin(elapsed * 0.001 + cell.phase + cell.seed * 0.011) * 0.5;
            let brightness = 0.012
                + cell.grain * 0.016
                + idleFlow * (0.018 + breath * 0.026)
                + grainBreath * (0.01 + slowBreath * 0.014)
                + fieldCharge * 0.025;
            let localShift = 0;

            if (hoverFade > 0) {
                const dx = cell.x - pointer.x;
                const dy = cell.y - pointer.y;
                const distance = Math.hypot(dx, dy);
                const ripple = (Math.sin(distance * 0.062 - elapsed * 0.006 + cell.phase) + 1) * 0.5;
                const falloff = Math.exp(-distance / (width < 700 ? 145 : 230));
                brightness += ripple * falloff * 0.18 * hoverFade;
            }

            let waveSum = 0;
            let waveEnergy = 0;
            let overlapA = 0;
            let overlapB = 0;
            let overlapPhaseA = 0;
            let overlapPhaseB = 0;

            for (const pulse of pulses) {
                const age = now - pulse.startedAt;
                const progress = Math.min(1, age / 3000);
                const radius = Math.min(maxRadius, 26 + progress * maxRadius);
                const dx = cell.x - pulse.x;
                const dy = cell.y - pulse.y;
                const distance = Math.hypot(dx, dy);
                const ringWidth = 26 + radius * 0.08;
                const ring = Math.exp(-Math.pow(distance - radius, 2) / (2 * ringWidth * ringWidth));
                const interior = distance < radius ? Math.max(0, 1 - distance / Math.max(radius, 1)) : 0;
                const decay = Math.max(0, 1 - age / 5200);
                const phase = distance * 0.118 - age * 0.013 + pulse.phase;
                const wave = Math.sin(phase) * ring * decay * pulse.strength;
                const energy = Math.abs(wave);

                waveSum += wave;
                waveEnergy += energy;
                brightness += interior * 0.08 * decay * pulse.strength;

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
                brightness += Math.max(0, constructive * 0.42 - destructive * 0.075);
                brightness += Math.min(0.18, waveEnergy * 0.07);

                if (overlapB > 0.05) {
                    const beat = 0.5 + Math.sin(overlapPhaseA - overlapPhaseB + cell.x * 0.044 - cell.y * 0.027) * 0.5;
                    brightness += beat * Math.min(0.24, overlapA * overlapB * 1.05);
                    localShift += Math.floor((beat + overlapA + overlapB) * 13);
                }
            }

            brightness = Math.min(0.92, brightness);
            if (brightness < 0.012) {
                continue;
            }

            const level = Math.max(0, Math.min(glyphRamp.length - 1, Math.floor(brightness * 8)));
            const options = glyphRamp[level];
            const stagger = 260 + (cell.seed % 210);
            const breathTick = Math.floor((elapsed + cell.phase * 900) / stagger);
            const glyph = options[(cell.seed + breathTick + charShift + localShift) % options.length];
            const alpha = Math.min(0.86, 0.025 + brightness * 0.82);
            const cool = localShift > 0 && brightness > 0.22;

            ctx.fillStyle = cool
                ? `rgba(220, 246, 255, ${alpha})`
                : `rgba(238, 238, 238, ${alpha})`;
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
        fieldCharge = Math.min(0.72, fieldCharge + 0.14);
        charShift = (charShift + 5 + Math.floor(Math.random() * 9)) % 997;
        lastClickAt = now;
        pulses.push({
            x: event.clientX,
            y: event.clientY,
            startedAt: now,
            strength: Math.min(1.35, 1 + pulses.length * 0.08),
            shift: charShift,
            phase: Math.random() * Math.PI * 2
        });
        pulses = pulses.slice(-8);
    }

    window.addEventListener("resize", resizeCanvas, { passive: true });
    window.addEventListener("pointermove", updatePointer, { passive: true });
    window.addEventListener("pointerdown", triggerPulse, { passive: true });
    window.addEventListener("pointerleave", () => {
        pointer.active = false;
    });

    resizeCanvas();
    requestAnimationFrame(draw);
})();

(function () {
    const targetSelectors = [
        ".split-section > .section-copy",
        ".split-section > .flow-map",
        ".capability-section > .section-heading",
        ".capability-card",
        ".api-section > .section-copy",
        ".terminal-panel",
        ".entry-section > .section-heading",
        ".entry-card"
    ];
    let elements = [];
    let ticking = false;

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function easeOutCubic(value) {
        return 1 - Math.pow(1 - value, 3);
    }

    function currentRiseY(element) {
        const value = parseFloat(element.style.getPropertyValue("--scroll-rise-y"));
        return Number.isFinite(value) ? value : 0;
    }

    function updateScrollRise() {
        ticking = false;

        const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 800;
        const scrollY = window.scrollY || document.documentElement.scrollTop || 0;
        const scrollHeight = Math.max(
            document.body.scrollHeight,
            document.documentElement.scrollHeight
        );
        const atDocumentBottom = scrollHeight - (scrollY + viewportHeight) <= 4;
        const startLine = viewportHeight * 0.96;
        const settleLine = viewportHeight * 0.48;
        const travelSpan = Math.max(180, startLine - settleLine);

        elements.forEach((element, index) => {
            const rect = element.getBoundingClientRect();
            const previousY = currentRiseY(element);
            const naturalTop = rect.top - previousY;
            const naturalBottom = rect.bottom - previousY;
            const stagger = Math.min(72, (index % 4) * 18);
            let rawProgress = (startLine - naturalTop - stagger) / travelSpan;

            if (atDocumentBottom && naturalBottom > 0 && naturalTop < viewportHeight) {
                rawProgress = 1;
            }

            const progress = easeOutCubic(clamp(rawProgress, 0, 1));
            const settledProgress = progress > 0.985 ? 1 : progress;
            const baseOffset = element.classList.contains("capability-card") || element.classList.contains("entry-card")
                ? 92
                : 118;
            const y = (1 - settledProgress) * baseOffset;
            const opacity = 0.02 + settledProgress * 0.98;
            const blur = settledProgress >= 1 ? 0 : (1 - settledProgress) * 10;

            element.style.setProperty("--scroll-rise-y", `${y.toFixed(2)}px`);
            element.style.setProperty("--scroll-rise-opacity", opacity.toFixed(3));
            element.style.setProperty("--scroll-rise-blur", `${blur.toFixed(2)}px`);
        });
    }

    function requestUpdate() {
        if (ticking) {
            return;
        }
        ticking = true;
        requestAnimationFrame(updateScrollRise);
    }

    function initScrollRise() {
        const seen = new Set();
        elements = [];

        targetSelectors.forEach((selector) => {
            document.querySelectorAll(selector).forEach((element) => {
                if (!seen.has(element)) {
                    seen.add(element);
                    elements.push(element);
                }
            });
        });

        elements.forEach((element) => {
            element.classList.add("scroll-rise");
        });

        document.documentElement.dataset.homeScrollRise = elements.length ? "js" : "empty";
        window.addEventListener("scroll", requestUpdate, { passive: true });
        window.addEventListener("resize", requestUpdate, { passive: true });
        window.setTimeout(requestUpdate, 120);
        requestUpdate();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initScrollRise, { once: true });
    } else {
        initScrollRise();
    }
})();

(function () {
    const config = window.__APP_CONFIG__ || {};
    const checks = [
        {
            elementId: "status-education",
            url: `${normalizeBaseUrl(config.educationApiBaseUrl, "http://127.0.0.1:8001")}/api/health`
        },
        {
            elementId: "status-maintenance",
            url: `${normalizeBaseUrl(config.maintenanceApiBaseUrl, "http://127.0.0.1:8002")}/api/health`
        },
        {
            elementId: "status-admin",
            url: `${normalizeBaseUrl(config.backendAdminBaseUrl, "http://127.0.0.1:8080")}/admin`
        }
    ];

    function normalizeBaseUrl(value, fallback) {
        return (value || fallback).replace(/\/+$/, "");
    }

    function setState(elementId, state) {
        const dot = document.getElementById(elementId);
        if (dot) {
            dot.dataset.state = state;
        }
    }

    checks.forEach((check) => {
        const controller = new AbortController();
        const timer = window.setTimeout(() => controller.abort(), 1800);

        fetch(check.url, {
            method: "GET",
            mode: "cors",
            cache: "no-store",
            signal: controller.signal
        })
            .then((response) => {
                setState(check.elementId, response.ok ? "online" : "offline");
            })
            .catch(() => {
                setState(check.elementId, "offline");
            })
            .finally(() => {
                window.clearTimeout(timer);
            });
    });
})();

(function () {
    const copyButton = document.querySelector("[data-copy-api]");
    const snippet = document.getElementById("api-snippet");
    if (!copyButton || !snippet) {
        return;
    }

    copyButton.addEventListener("click", async () => {
        const originalText = copyButton.textContent;
        try {
            await navigator.clipboard.writeText(snippet.innerText.trim());
            copyButton.textContent = "已复制";
        } catch (error) {
            copyButton.textContent = "复制失败";
        }
        window.setTimeout(() => {
            copyButton.textContent = originalText;
        }, 1200);
    });
})();
