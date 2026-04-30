(function () {
    "use strict";

    var renderQueued = false;
    var rendering = false;
    var pendingRoots = [];

    var delimiters = [
        { left: "\\begin{equation}", right: "\\end{equation}", display: true },
        { left: "\\begin{equation*}", right: "\\end{equation*}", display: true },
        { left: "\\begin{align}", right: "\\end{align}", display: true },
        { left: "\\begin{align*}", right: "\\end{align*}", display: true },
        { left: "\\begin{gather}", right: "\\end{gather}", display: true },
        { left: "\\begin{gather*}", right: "\\end{gather*}", display: true },
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
        { left: "$", right: "$", display: false }
    ];

    var fallbackCommandMap = {
        "\\alpha": "\u03b1",
        "\\beta": "\u03b2",
        "\\gamma": "\u03b3",
        "\\delta": "\u03b4",
        "\\epsilon": "\u03b5",
        "\\theta": "\u03b8",
        "\\lambda": "\u03bb",
        "\\mu": "\u03bc",
        "\\pi": "\u03c0",
        "\\rho": "\u03c1",
        "\\sigma": "\u03c3",
        "\\phi": "\u03c6",
        "\\omega": "\u03c9",
        "\\Gamma": "\u0393",
        "\\Delta": "\u0394",
        "\\Theta": "\u0398",
        "\\Lambda": "\u039b",
        "\\Pi": "\u03a0",
        "\\Sigma": "\u03a3",
        "\\Phi": "\u03a6",
        "\\Omega": "\u03a9",
        "\\times": "\u00d7",
        "\\cdot": "\u00b7",
        "\\leq": "\u2264",
        "\\geq": "\u2265",
        "\\neq": "\u2260",
        "\\approx": "\u2248",
        "\\infty": "\u221e",
        "\\sum": "\u2211",
        "\\prod": "\u220f",
        "\\int": "\u222b",
        "\\rightarrow": "\u2192",
        "\\Rightarrow": "\u21d2"
    };

    var bareLatexRegex = /\\(?:frac\s*\{[^{}]+\}\s*\{[^{}]+\}|sqrt\s*\{[^{}]+\}|(?:bar|overline|hat|vec|tilde|text|operatorname|mathbb|mathcal|mathbf|mathrm)\s*\{[^{}]+\}|(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|rho|sigma|phi|omega|Gamma|Delta|Theta|Lambda|Pi|Sigma|Phi|Omega|partial|nabla|times|cdot|leq|geq|neq|approx|infty|sum|prod|int|rightarrow|Rightarrow)\b)(?:\s*[_^]\s*(?:\{[^{}]+\}|[A-Za-z0-9+\-]+))*/g;

    function canRender() {
        return typeof window.renderMathInElement === "function";
    }

    function normalizeLatexText(value) {
        return String(value == null ? "" : value)
            .replace(/\\\\([()[\]])/g, "\\$1")
            .replace(/\\\\([A-Za-z]+)/g, "\\$1")
            .replace(/\\\\([{}_^])/g, "\\$1")
            .replace(/\\\\begin\{/g, "\\begin{")
            .replace(/\\\\end\{/g, "\\end{");
    }

    function isIgnoredElement(node) {
        return Boolean(
            node &&
            node.nodeType === 1 &&
            node.closest &&
            node.closest("textarea, pre, code, script, style, option, svg, canvas, .katex, .katex-display, .latex-fallback, .no-latex")
        );
    }

    function simplifyLatex(source) {
        var text = String(source || "").trim();
        if (text.indexOf("$$") === 0) {
            text = text.slice(2, -2);
        } else if (text.indexOf("\\begin{") === 0) {
            text = text.replace(/^\\begin\{[^}]+\}/, "").replace(/\\end\{[^}]+\}$/, "");
        } else if (text.indexOf("\\[") === 0 || text.indexOf("\\(") === 0) {
            text = text.slice(2, -2);
        } else if (text.charAt(0) === "$") {
            text = text.slice(1, -1);
        }

        text = text.replace(/\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, "($1)/($2)");
        text = text.replace(/\\sqrt\s*\{([^{}]+)\}/g, "\u221a($1)");
        text = text.replace(/\\text\s*\{([^{}]+)\}/g, "$1");
        text = text.replace(/\\operatorname\s*\{([^{}]+)\}/g, "$1");

        Object.keys(fallbackCommandMap).forEach(function (command) {
            text = text.split(command).join(fallbackCommandMap[command]);
        });

        text = text.replace(/\s+/g, " ").trim();
        return text || source;
    }

    function createFallbackNode(token) {
        var display = token.indexOf("$$") === 0 || token.indexOf("\\[") === 0;
        var node = document.createElement(display ? "div" : "span");
        node.className = display ? "latex-fallback latex-fallback-display" : "latex-fallback";
        node.textContent = simplifyLatex(token);
        node.title = token;
        return node;
    }

    function createKatexNode(token) {
        if (window.katex && typeof window.katex.renderToString === "function") {
            try {
                var node = document.createElement("span");
                node.innerHTML = window.katex.renderToString(token, {
                    displayMode: false,
                    throwOnError: false,
                    strict: "ignore",
                    trust: false
                });
                return node;
            } catch (error) {
                if (window.console && typeof window.console.warn === "function") {
                    window.console.warn("Bare LaTeX render failed:", error);
                }
            }
        }
        return createFallbackNode(token);
    }

    function findMathParts(text) {
        var regex = /\\begin\{(equation\*?|align\*?|gather\*?)\}[\s\S]*?\\end\{\1\}|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|(^|[^\\])\$[^$\n]+?\$/g;
        var parts = [];
        var lastIndex = 0;
        var match;

        while ((match = regex.exec(text)) !== null) {
            var raw = match[0];
            var tokenOffset = 0;
            if (raw.charAt(0) !== "$" && raw.charAt(0) !== "\\") {
                tokenOffset = 1;
            }

            var tokenStart = match.index + tokenOffset;
            if (tokenStart > lastIndex) {
                parts.push({ type: "text", value: text.slice(lastIndex, tokenStart) });
            }

            parts.push({ type: "math", value: text.slice(tokenStart, match.index + raw.length) });
            lastIndex = match.index + raw.length;
        }

        if (lastIndex < text.length) {
            parts.push({ type: "text", value: text.slice(lastIndex) });
        }

        return parts;
    }

    function fallbackRenderLatexIn(root) {
        var target = root || document.body;
        if (!target || !document.createTreeWalker) {
            return;
        }

        var walker = document.createTreeWalker(
            target,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function (node) {
                    if (!node.nodeValue || node.nodeValue.indexOf("$") === -1 && node.nodeValue.indexOf("\\") === -1) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    if (isIgnoredElement(node.parentElement)) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    return NodeFilter.FILTER_ACCEPT;
                }
            }
        );

        var textNodes = [];
        var current;
        while ((current = walker.nextNode())) {
            textNodes.push(current);
        }

        textNodes.forEach(function (node) {
            var normalizedText = normalizeLatexText(node.nodeValue);
            var parts = findMathParts(normalizedText);
            if (parts.length <= 1 && (!parts[0] || parts[0].type !== "math")) {
                return;
            }

            var fragment = document.createDocumentFragment();
            parts.forEach(function (part) {
                if (part.type === "math") {
                    fragment.appendChild(createFallbackNode(part.value));
                } else if (part.value) {
                    fragment.appendChild(document.createTextNode(part.value));
                }
            });
            node.parentNode.replaceChild(fragment, node);
        });
    }

    function renderBareLatexIn(root) {
        var target = root || document.body;
        if (!target || !document.createTreeWalker) {
            return;
        }

        var walker = document.createTreeWalker(
            target,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function (node) {
                    if (!node.nodeValue || node.nodeValue.indexOf("\\") === -1) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    if (isIgnoredElement(node.parentElement)) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    bareLatexRegex.lastIndex = 0;
                    return bareLatexRegex.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                }
            }
        );

        var textNodes = [];
        var current;
        while ((current = walker.nextNode())) {
            textNodes.push(current);
        }

        textNodes.forEach(function (node) {
            var text = normalizeLatexText(node.nodeValue);
            bareLatexRegex.lastIndex = 0;
            var fragment = document.createDocumentFragment();
            var lastIndex = 0;
            var match;
            while ((match = bareLatexRegex.exec(text)) !== null) {
                if (match.index > lastIndex) {
                    fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
                }
                fragment.appendChild(createKatexNode(match[0]));
                lastIndex = match.index + match[0].length;
            }
            if (lastIndex < text.length) {
                fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
            }
            if (fragment.childNodes.length && node.parentNode) {
                node.parentNode.replaceChild(fragment, node);
            }
        });
    }

    function renderLatexIn(root) {
        var target = root || document.body;
        if (!target || rendering) {
            return;
        }

        rendering = true;
        try {
            normalizeLatexTextNodes(target);
            if (canRender()) {
                window.renderMathInElement(target, {
                    delimiters: delimiters,
                    throwOnError: false,
                    strict: "ignore",
                    trust: false,
                    ignoredTags: [
                        "script",
                        "noscript",
                        "style",
                        "textarea",
                        "pre",
                        "code",
                        "option",
                        "svg",
                        "canvas"
                    ],
                    ignoredClasses: [
                        "katex",
                        "katex-display",
                        "latex-fallback",
                        "no-latex",
                        "tex2jax_ignore"
                    ]
                });
                renderBareLatexIn(target);
            } else {
                fallbackRenderLatexIn(target);
                renderBareLatexIn(target);
            }
        } catch (error) {
            if (window.console && typeof window.console.warn === "function") {
                window.console.warn("LaTeX render failed:", error);
            }
        } finally {
            rendering = false;
        }
    }

    function normalizeLatexTextNodes(root) {
        var target = root || document.body;
        if (!target || !document.createTreeWalker) {
            return;
        }
        var walker = document.createTreeWalker(
            target,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function (node) {
                    if (!node.nodeValue || node.nodeValue.indexOf("\\\\") === -1 || isIgnoredElement(node.parentElement)) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    return NodeFilter.FILTER_ACCEPT;
                }
            }
        );
        var nodes = [];
        var current;
        while ((current = walker.nextNode())) {
            nodes.push(current);
        }
        nodes.forEach(function (node) {
            var normalized = normalizeLatexText(node.nodeValue);
            if (normalized !== node.nodeValue) {
                node.nodeValue = normalized;
            }
        });
    }

    function isRenderableRoot(node) {
        if (!node) {
            return false;
        }
        var element = node.nodeType === 1 ? node : node.parentElement;
        if (!element || isIgnoredElement(element)) {
            return false;
        }
        return Boolean(
            element.matches &&
            (
                element.matches(".markdown-body, .markdown-inline, .latex-auto, .answer-box, .course-content, .lecture-content-display, .exercise-content, #exercise-content, #detail-content, #node-detail-content, .modal-content, .exercise-review-list, .exercise-review-card, .exercise-review-option, .exercise-review-option-text, .exercise-review-question, .exercise-review-explanation") ||
                element.closest(".markdown-body, .markdown-inline, .latex-auto, .answer-box, .course-content, .lecture-content-display, .exercise-content, #exercise-content, #detail-content, #node-detail-content, .modal-content, .exercise-review-list, .exercise-review-card, .exercise-review-option, .exercise-review-option-text, .exercise-review-question, .exercise-review-explanation")
            )
        );
    }

    function findRenderableRoot(node) {
        var element = node && node.nodeType === 1 ? node : node && node.parentElement;
        if (!element || isIgnoredElement(element)) {
            return null;
        }
        if (element.matches(".markdown-body, .markdown-inline, .latex-auto, .answer-box, .course-content, .lecture-content-display, .exercise-content, #exercise-content, #detail-content, #node-detail-content, .modal-content, .exercise-review-list, .exercise-review-card, .exercise-review-option, .exercise-review-option-text, .exercise-review-question, .exercise-review-explanation")) {
            return element;
        }
        var closest = element.closest(".markdown-body, .markdown-inline, .latex-auto, .answer-box, .course-content, .lecture-content-display, .exercise-content, #exercise-content, #detail-content, #node-detail-content, .modal-content, .exercise-review-list, .exercise-review-card, .exercise-review-option, .exercise-review-option-text, .exercise-review-question, .exercise-review-explanation");
        if (closest) {
            return closest;
        }
        return element.querySelector(".markdown-body, .markdown-inline, .latex-auto, .answer-box, .course-content, .lecture-content-display, .exercise-content, #exercise-content, #detail-content, #node-detail-content, .modal-content, .exercise-review-list, .exercise-review-card, .exercise-review-option, .exercise-review-option-text, .exercise-review-question, .exercise-review-explanation");
    }

    function addPendingRoot(nextRoot) {
        var next = nextRoot || document.body;
        if (!next || isIgnoredElement(next)) {
            return;
        }

        pendingRoots = pendingRoots.filter(function (root) {
            return root && document.documentElement.contains(root);
        });

        for (var i = 0; i < pendingRoots.length; i++) {
            var root = pendingRoots[i];
            if (root === next || root.contains(next)) {
                return;
            }
            if (next.contains && next.contains(root)) {
                pendingRoots[i] = next;
                return;
            }
        }

        pendingRoots.push(next);
    }

    function scheduleLatexRender(root) {
        addPendingRoot(root);
        if (renderQueued) {
            return;
        }

        renderQueued = true;
        window.requestAnimationFrame(function () {
            var targets = pendingRoots.length ? pendingRoots.slice() : [document.body];
            renderQueued = false;
            pendingRoots = [];
            targets.forEach(function (target) {
                renderLatexIn(target);
            });
        });
    }

    function shouldIgnoreNode(node) {
        if (!node || node.nodeType !== 1) {
            return false;
        }
        return isIgnoredElement(node);
    }

    window.renderLatexIn = renderLatexIn;
    window.scheduleLatexRender = scheduleLatexRender;

    document.addEventListener("DOMContentLoaded", function () {
        scheduleLatexRender(document.body);

        if (typeof MutationObserver !== "function") {
            return;
        }

        var observer = new MutationObserver(function (mutations) {
            if (rendering) {
                return;
            }

            var roots = [];
            mutations.forEach(function (mutation) {
                if (shouldIgnoreNode(mutation.target)) {
                    return;
                }
                if (mutation.type === "characterData") {
                    var textRoot = findRenderableRoot(mutation.target);
                    if (textRoot) roots.push(textRoot);
                    return;
                }
                Array.prototype.forEach.call(mutation.addedNodes || [], function (node) {
                    if (node.nodeType !== 1 && node.nodeType !== 3) {
                        return;
                    }
                    if (node.nodeType === 3 && !isRenderableRoot(node)) {
                        return;
                    }
                    var root = findRenderableRoot(node);
                    if (root) roots.push(root);
                });
            });

            roots.forEach(scheduleLatexRender);
        });

        observer.observe(document.body, {
            childList: true,
            characterData: true,
            subtree: true
        });
    });
})();
