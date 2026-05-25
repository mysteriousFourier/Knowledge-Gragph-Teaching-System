$(function () {
  "use strict";

  var editor = CodeMirror.fromTextArea(document.getElementById("editor"), {
    mode: "stex",
    theme: "monokai",
    lineNumbers: true,
    lineWrapping: true,
    readOnly: false,
  });

  var isGenerating = false;
  var fullLatex = "";
  var sourceLatex = "";
  var slidesData = null;
  var currentSlideIdx = -1;
  var activeTab = "latex";
  var lastFocusedInput = null;
  var lastFocusedTextbox = null;
  var lastFocusedRichText = null;
  var savedRichTextRange = null;
  var latexSyncTimer = null;
  var currentCustomRequirements = "";
  var historyTimer = null;
  var undoStack = [];
  var redoStack = [];
  var historyLock = false;
  var HISTORY_LIMIT = 4;
  var REVIEW_BACKGROUND_LATEX_PREFIX = [
    "{",
    "% 设置全页背景：灰色 + 中心白色渐变矩形",
    "\\setbeamertemplate{background}{%",
    "  \\begin{tikzpicture}[remember picture, overlay]",
    "    \\def\\topheight{1cm}             %顶部灰色块保留高度",
    "    \\def\\height{2cm}               % 梯形高度",
    "    \\def\\backcolor{gray!30}",
    "    \\def\\frontcolor{white}",
    "    \\fill[\\backcolor] (current page.south west) rectangle (current page.north east);",
    "        %\\shade[shading=radial, inner color=white, outer color=red]",
    "      %({0.5\\paperwidth-7cm}, {0.5\\paperheight-13cm}) rectangle + (14cm,7cm);",
    "    \\fill[\\frontcolor] ([xshift=0.5\\height, yshift=0.5\\height] current page.south west)",
    "             rectangle ([xshift=-0.5\\height, yshift=-0.5\\height-\\topheight] current page.north east);",
    "    % 上底两端：页面左、右边界，距离页面顶部向下 5cm",
    "    \\coordinate (UL1) at ([yshift=-\\topheight] current page.north west);",
    "    \\coordinate (UR1) at ([yshift=-\\topheight] current page.north east);",
    "",
    "    % 下底两端：从上底两端垂直向下 \\height，再向内缩 \\offset",
    "    \\coordinate (DL1) at ([xshift=\\height,yshift=-\\height] UL1);",
    "    \\coordinate (DR1) at ([xshift=-\\height,yshift=-\\height] UR1);",
    "",
    "    \\coordinate (DL2) at (current page.south west);                     % 下底左端",
    "    \\coordinate (DR2) at (current page.south east);           % 下底右端",
    "    \\coordinate (UL2) at ([xshift=\\height, yshift=\\height] DL2); % 上底左端（向右向上各移 \\h）",
    "    \\coordinate (UR2) at ([xshift=-\\height, yshift=\\height] DR2);% 上底右端（向左向上各移 \\h）",
    "    ",
    "    % 绘制渐变梯形",
    "    \\shade[top color=\\backcolor, bottom color=\\frontcolor]",
    "       (UL1) -- (UR1) -- (DR1) -- (DL1) -- cycle;",
    "    \\shade[top color=\\frontcolor, bottom color=\\backcolor]",
    "      (UL2) -- (UR2) -- (DR2) -- (DL2) -- cycle;",
    "    \\shade[left color=\\backcolor, right color=\\frontcolor]",
    "      (DL2) -- (UL1) -- (DL1) -- (UL2) -- cycle; %左下 -- 左上 -- 右上 -- 右下",
    "    \\shade[left color=\\frontcolor, right color=\\backcolor]",
    "      (UR2) -- (DR1) -- (UR1) -- (DR2) -- cycle; %左下 -- 左上 -- 右上 -- 右下",
    "  \\end{tikzpicture}%",
    "}",
    "",
    "% 复习内容空白幻灯",
  ].join("\n");
  var savedLectureChapters = [];
  var savedPptProjects = [];
  var savedSlideDragPayload = null;
  var savedPptGalleryManualPosition = null;
  var slideThumbDragIndex = null;
  var inputCollapsed = localStorage.getItem("bg_input_panel_collapsed") === "1";
  var latexSyncMap = {};
  var latexSyncMarks = [];
  var currentSyncKey = "";
  var latexSelectionTimer = null;
  var syncSelectionLock = false;
  var pptSyncHighlightTimer = null;
  var latexProgrammaticUpdate = false;
  var latexManualSyncTimer = null;
  var latexManualSyncSeq = 0;
  var suppressNextLatexManualSync = false;
  var latexGenerateProgress = 0;
  var importedPackageImages = [];
  var packageImagePanelOpen = false;
  var editedImageGeometry = { placeholders: {}, images: {} };
  var rawMarkdownContent = "";
  var importedPackageAssetUrls = {};
  var packageImageViewerOpen = false;
  var figurePreviewMap = {};
  var figureHoverPreviewOpen = false;
  var latexPptSplitRatio = parseFloat(localStorage.getItem("bg_latex_ppt_split_ratio") || "0.5");
  if (Number.isNaN(latexPptSplitRatio)) latexPptSplitRatio = 0.5;
  latexPptSplitRatio = Math.max(0.25, Math.min(0.75, latexPptSplitRatio));
  var collapsedPaneResize = null;

  function refreshEditorSize() {
    if (editor && editor.refresh) {
      setTimeout(function () {
        editor.refresh();
      }, 0);
    }
  }

  function hasMathSyntax(text) {
    return /\\\(|\\\[|\$\$|(^|[^\\])\$|\\begin\{|\\(?:frac|sqrt|sum|prod|int|beta|alpha|gamma|delta|theta|lambda|mu|sigma|phi|omega|bar|overline|hat|vec|tilde|partial|nabla|cdot|times|leq|geq|neq|approx|infty)\b|[_^]\s*\{?/.test(String(text || ""));
  }

  function normalizePackageAssetKey(rawTarget) {
    var normalized = String(rawTarget || "").trim().replace(/^["']|["']$/g, "");
    if (/^(https?:\/\/|data:|\/)/i.test(normalized)) return "";
    return normalized.replace(/^\.\//, "").replace(/\\/g, "/").split("?")[0].split("#")[0];
  }

  function resolvePackageAssetUrl(rawTarget) {
    var normalized = normalizePackageAssetKey(rawTarget);
    if (!normalized) {
      var direct = String(rawTarget || "").trim();
      if (/^\/beamer-generator\/uploads\//i.test(direct) || /^\/uploads\//i.test(direct)) return direct;
      return "";
    }
    var candidates = [normalized];
    if (normalized.indexOf("figures/") === 0) {
      candidates.push(normalized.slice("figures/".length));
    }
    if (normalized.indexOf("/") !== -1) {
      candidates.push(normalized.split("/").pop());
    }
    for (var i = 0; i < candidates.length; i++) {
      if (importedPackageAssetUrls[candidates[i]]) return importedPackageAssetUrls[candidates[i]];
    }
    return "";
  }

  function findNearbyFigureLabel(lines, index) {
    var start = Math.max(0, index - 4);
    var end = Math.min(lines.length - 1, index + 2);
    for (var i = index; i >= start; i--) {
      var m = String(lines[i] || "").match(/(?:Figure|Fig\.?|图)\s*\d+(?:\.\d+)?/i);
      if (m) return extractFigureReference(m[0]);
    }
    for (var j = index + 1; j <= end; j++) {
      var m2 = String(lines[j] || "").match(/(?:Figure|Fig\.?|图)\s*\d+(?:\.\d+)?/i);
      if (m2) return extractFigureReference(m2[0]);
    }
    return "";
  }

  function normalizeFigureLabel(label) {
    return String(label || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function extractFigureReference(text) {
    var s = String(text || "");
    var m = s.match(/(?:Figure|Fig\.?|图)\s*\d+(?:\.\d+)?/i);
    if (!m) return "";
    var num = (m[0].match(/\d+(?:\.\d+)?/) || [""])[0];
    return num ? "Figure " + num : m[0];
  }

  function collectFigureReferences(text) {
    var refs = [];
    var seen = {};
    var pattern = /(?:Figure|Fig\.?|图)\s*\d+(?:\.\d+)?/ig;
    var match;
    while ((match = pattern.exec(String(text || ""))) !== null) {
      var label = extractFigureReference(match[0]);
      var key = normalizeFigureLabel(label);
      if (!key || seen[key]) continue;
      seen[key] = true;
      refs.push(label);
    }
    return refs;
  }

  function normalizeAssetStem(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  }

  function pickPackageImageForFigure(label) {
    var labelKey = normalizeFigureLabel(label);
    var digits = labelKey.replace(/[^0-9]/g, "");
    var dotted = (labelKey.match(/\d+(?:\.\d+)?/) || [""])[0];
    var dashed = dotted.replace(/\./g, "-");
    var underscored = dotted.replace(/\./g, "_");
    var compact = normalizeAssetStem(labelKey);
    var best = "";

    for (var i = 0; i < importedPackageImages.length; i++) {
      var img = importedPackageImages[i];
      var rawName = String((img && img.name) || "").toLowerCase();
      var stem = normalizeAssetStem(rawName);
      if (!stem) continue;
      var figureNamedFile = rawName.indexOf("figure") !== -1 || rawName.indexOf("fig") !== -1;
      if (figureNamedFile && dotted && rawName.indexOf(dotted) !== -1) return img.url;
      if (figureNamedFile && dashed && rawName.indexOf(dashed) !== -1) return img.url;
      if (figureNamedFile && underscored && rawName.indexOf(underscored) !== -1) return img.url;
      if (figureNamedFile && digits && stem.indexOf(digits) !== -1) return img.url;
      if (figureNamedFile && compact && stem.indexOf(compact) !== -1) return img.url;
      if (!best && figureNamedFile && digits && stem.replace(/figure/g, "").indexOf(digits) !== -1) {
        best = img.url;
      }
    }

    return best;
  }

  function buildFigurePreviewMap() {
    figurePreviewMap = {};
    var source = rawMarkdownContent || "";
    if (!source && !importedPackageImages.length) return;
    var lines = String(source).split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i] || "";
      var match = line.match(/!\[([^\]]*)\]\(([^)]+)\)/i);
      if (!match) continue;
      var labelMatch = match[1].match(/(?:Figure|Fig\.?|图)\s*\d+(?:\.\d+)?/i) || line.match(/(?:Figure|Fig\.?|图)\s*\d+(?:\.\d+)?/i);
      var label = labelMatch ? extractFigureReference(labelMatch[0]) : findNearbyFigureLabel(lines, i);
      if (!label) continue;
      var url = resolvePackageAssetUrl(match[2]);
      if (!url) continue;
      var caption = "";
      for (var j = i + 1; j < lines.length; j++) {
        var nextLine = String(lines[j] || "").trim();
        if (!nextLine) continue;
        caption = nextLine.replace(/^>\s*/, "").replace(/^\*\*|\*\*$/g, "");
        break;
      }
      figurePreviewMap[normalizeFigureLabel(label)] = {
        label: label,
        url: url,
        assetUrl: match[2],
        caption: caption || label,
      };
    }

  }

  function buildFigureAssetPayload() {
    var payload = {};
    Object.keys(figurePreviewMap).forEach(function (key) {
      var figure = figurePreviewMap[key];
      if (!figure || !figure.url) return;
      payload[figure.label || key] = figure.url;
    });
    if (slidesData && slidesData.slides) {
      slidesData.slides.forEach(function (slide) {
        slideFigureRefs(slide).forEach(function (ref) {
          if (payload[ref]) return;
          var key = normalizeFigureLabel(ref);
          var figure = figurePreviewMap[key] || null;
          var url = (figure && figure.url) || pickPackageImageForFigure(ref);
          if (url) payload[ref] = url;
        });
      });
    }
    return payload;
  }

  function appendTextNode($target, text) {
    var source = String(text || "").replace(/\\\\(?:\[[^\]]*\])?/g, " ");
    var pattern = /((?:Figure|Fig\.?|图)\s*\d+(?:\.\d+)?)/gi;
    var lastIndex = 0;
    var match;

    while ((match = pattern.exec(source)) !== null) {
      if (match.index > lastIndex) {
        $target.append(document.createTextNode(source.slice(lastIndex, match.index)));
      }

      var label = extractFigureReference(match[1]);
      var key = normalizeFigureLabel(label);
      var figure = figurePreviewMap[key];
      var span = document.createElement("span");
      span.className = "figure-ref" + (figure ? " has-figure-preview" : "");
      span.setAttribute("data-figure-key", key);
      span.textContent = label;
      if (figure && figure.caption) {
        span.setAttribute("data-figure-caption", figure.caption);
      }
      $target.append(span);
      lastIndex = pattern.lastIndex;
    }

    if (lastIndex < source.length) {
      $target.append(document.createTextNode(source.slice(lastIndex)));
    }
  }

  function normalizeKatexFormula(formula, displayMode) {
    var s = String(formula || "").trim();
    if (!s) return "";
    s = s
      .replace(/\\nonumber\b/g, "")
      .replace(/\\label\{[^}]*\}/g, "")
      .replace(/\\\\\[[^\]]*\]/g, "\\\\")
      .replace(/\s+/g, " ")
      .trim();

    var tag = "";
    s = s.replace(/\\tag\{([^}]*)\}/g, function (_match, value) {
      tag = "\\tag{" + value + "}";
      return "";
    }).trim();

    var needsAligned = displayMode && !/\\begin\{/.test(s) && (s.indexOf("&") !== -1 || /\\\\/.test(s));
    if (needsAligned) {
      s = "\\begin{aligned}" + s + "\\end{aligned}";
    }
    if (tag) s += tag;
    return s;
  }

  function appendKatexNode($target, formula, displayMode, originalText, extraClass) {
    var span = document.createElement(displayMode ? "div" : "span");
    span.className = (displayMode ? "katex-display" : "") + (extraClass ? " " + extraClass : "");
    if (extraClass && extraClass.indexOf("slide-inline-formula-box") !== -1) {
      span.setAttribute("contenteditable", "false");
      span.setAttribute("data-latex", originalText || formula || "");
    }
    try {
      if (!window.katex) throw new Error("KaTeX unavailable");
      window.katex.render(normalizeKatexFormula(formula, displayMode), span, {
        displayMode: !!displayMode,
        throwOnError: false,
        strict: "ignore",
        trust: false,
      });
    } catch (err) {
      span.textContent = originalText || formula || "";
    }
    $target.append(span);
  }

  function latexSourceForRenderedFormula(formula, displayMode) {
    var source = String(formula || "").trim();
    if (!source) return "";
    if (/^(\\\(|\\\[|\$\$|\$)/.test(source)) return source;
    return displayMode ? "\\[" + source + "\\]" : "$" + source + "$";
  }

  function renderMathText($target, text, options) {
    var source = repairPptLatexArtifacts(text);
    var opts = options || {};
    $target.empty();
    $target.toggleClass("muted", !source.trim());
    if (!source.trim()) {
      $target.text(opts.emptyText || "");
      return;
    }

    var normalized = source
      .replace(/\\\\\[[^\]]*\]/g, " ")
      .replace(/\\\\\(/g, "\\(")
      .replace(/\\\\\)/g, "\\)");
    var pattern = /\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|\$\$([\s\S]*?)\$\$|(^|[^\\])\$([^$\n]+?)\$/g;
    var lastIndex = 0;
    var matched = false;
    var match;

    while ((match = pattern.exec(normalized)) !== null) {
      var prefix = match[4] || "";
      var matchStart = match.index + prefix.length;
      appendTextNode($target, normalized.slice(lastIndex, matchStart));
      var formula = match[1] || match[2] || match[3] || match[5] || "";
      var displayMode = Boolean(match[1] || match[3]);
      appendKatexNode($target, formula, displayMode, normalized.slice(matchStart, pattern.lastIndex), opts.boxedMath ? "slide-inline-formula-box" : "");
      lastIndex = pattern.lastIndex;
      matched = true;
    }

    appendTextNode($target, normalized.slice(lastIndex));

    if (!matched && hasMathSyntax(normalized)) {
      $target.empty();
      var fallbackDisplayMode = opts.displayMode !== false;
      appendKatexNode(
        $target,
        normalized.trim(),
        fallbackDisplayMode,
        latexSourceForRenderedFormula(normalized, fallbackDisplayMode),
        opts.boxedMath ? "slide-inline-formula-box" : ""
      );
    }
  }

  function extractMathFormulaSnippets(text) {
    var source = String(text || "");
    var snippets = [];
    var seen = {};

    function add(formula, displayMode) {
      var clean = String(formula || "").trim();
      if (!clean) return;
      clean = clean.replace(/^\\\[/, "").replace(/\\\]$/, "");
      clean = clean.replace(/^\\\(/, "").replace(/\\\)$/, "");
      clean = clean.replace(/^\$\$/, "").replace(/\$\$$/, "");
      clean = clean.replace(/^\$/, "").replace(/\$$/, "").trim();
      if (!clean || clean.length > 260) return;
      var key = clean.replace(/\s+/g, "");
      if (!key || seen[key]) return;
      seen[key] = true;
      snippets.push({ formula: clean, displayMode: !!displayMode });
    }

    var match;
    var delimited = /\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|\$\$([\s\S]*?)\$\$|(^|[^\\])\$([^$\n]+?)\$/g;
    while ((match = delimited.exec(source)) !== null) {
      add(match[1] || match[2] || match[3] || match[5] || "", Boolean(match[1] || match[3]));
    }

    if (!snippets.length && hasMathSyntax(source)) {
      var rawMath = /\\(?:frac|sqrt|sum|prod|int|lim|beta|alpha|gamma|delta|theta|lambda|mu|sigma|phi|omega|bar|overline|hat|vec|tilde|partial|nabla|cdot|times|leq|geq|neq|approx|infty)\b(?:\{[^{}]*\})?(?:\s*[_^]\s*\{?[\w\\]+\}?){0,3}|[A-Za-z](?:\s*[_^]\s*\{?[\w\\]+\}?)+/g;
      while ((match = rawMath.exec(source)) !== null) {
        add(match[0], false);
      }
    }

    return snippets;
  }

  function renderFormulaBoxes($target, text) {
    var snippets = extractMathFormulaSnippets(text);
    $target.empty().toggle(!!snippets.length);
    for (var i = 0; i < snippets.length; i++) {
      var item = snippets[i];
      var box = document.createElement("div");
      box.className = "slide-formula-box";
      appendKatexNode($(box), item.formula, item.displayMode, item.formula);
      $target.append(box);
    }
  }

  function serializeRichMathText(root) {
    var parts = [];
    function walk(node) {
      if (!node) return;
      if (node.nodeType === Node.TEXT_NODE) {
        parts.push(node.nodeValue || "");
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      var el = node;
      if (el.hasAttribute("data-latex")) {
        parts.push(el.getAttribute("data-latex") || "");
        return;
      }
      if (el.tagName === "BR") {
        parts.push("\n");
        return;
      }
      for (var i = 0; i < el.childNodes.length; i++) {
        walk(el.childNodes[i]);
      }
      if (el.tagName === "DIV" || el.tagName === "P") parts.push("\n");
    }
    walk(root);
    return parts.join("").replace(/\u00a0/g, " ").replace(/\n{3,}/g, "\n\n").trim();
  }

  function sanitizeRichTextHtml(root) {
    var clone = root.cloneNode(true);
    $(clone).find(".figure-ref").each(function () {
      this.removeAttribute("data-figure-caption");
    });
    return clone.innerHTML;
  }

  function cssColorToLatexSpec(value) {
    var s = String(value || "").trim();
    if (!s || s === "transparent" || s === "rgba(0, 0, 0, 0)") return "";
    if (s[0] === "#") {
      var hex = s.slice(1);
      if (hex.length === 3) hex = hex.split("").map(function (ch) { return ch + ch; }).join("");
      if (/^[0-9a-f]{6}$/i.test(hex)) return "[HTML]{" + hex.toUpperCase() + "}";
    }
    var m = s.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([0-9.]+))?\)/i);
    if (m && (m[4] === undefined || parseFloat(m[4]) > 0)) {
      var hexParts = [m[1], m[2], m[3]].map(function (part) {
        var n = Math.max(0, Math.min(255, parseInt(part, 10) || 0));
        return n.toString(16).padStart(2, "0").toUpperCase();
      });
      return "[HTML]{" + hexParts.join("") + "}";
    }
    return "";
  }

  function richHtmlToLatex(html, fallbackText) {
    var source = String(html || "").trim();
    if (!source) return escapeLatexTextPreservingMath(fallbackText || "");
    var root = document.createElement("div");
    root.innerHTML = source;

    function walk(node) {
      if (!node) return "";
      if (node.nodeType === Node.TEXT_NODE) {
        return escapeLatexTextPreservingMath(node.nodeValue || "");
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return "";
      var el = node;
      var tag = el.tagName ? el.tagName.toLowerCase() : "";
      if (el.hasAttribute("data-latex")) {
        return escapeLatexTextPreservingMath(el.getAttribute("data-latex") || "");
      }
      if (tag === "br") return "\\\\";
      var inner = "";
      for (var i = 0; i < el.childNodes.length; i++) {
        inner += walk(el.childNodes[i]);
      }
      if (!inner) return "";
      var colorSpec = cssColorToLatexSpec(el.style && el.style.color ? el.style.color : (el.getAttribute("color") || ""));
      var fontWeight = String(el.style && el.style.fontWeight || "").toLowerCase();
      var fontStyle = String(el.style && el.style.fontStyle || "").toLowerCase();
      if (tag === "b" || tag === "strong" || fontWeight === "bold" || parseInt(fontWeight, 10) >= 600) {
        inner = "\\textbf{" + inner + "}";
      }
      if (tag === "i" || tag === "em" || fontStyle === "italic") {
        inner = "\\textit{" + inner + "}";
      }
      if (colorSpec) {
        inner = "\\textcolor" + colorSpec + "{" + inner + "}";
      }
      if (tag === "div" || tag === "p") {
        inner += "\n";
      }
      return inner;
    }

    var out = "";
    for (var j = 0; j < root.childNodes.length; j++) out += walk(root.childNodes[j]);
    out = out.replace(/\n{3,}/g, "\n\n").trim();
    return out || escapeLatexTextPreservingMath(fallbackText || "");
  }

  function restoreRichTextHtml($preview, html, fallbackText) {
    if (html) {
      var probe = document.createElement("div");
      probe.innerHTML = html;
      if (serializeRichMathText(probe) === String(fallbackText || "").trim()) {
        $preview.html(html);
        return;
      }
    }
    renderMathText($preview, fallbackText || "", {
      displayMode: false,
      boxedMath: true,
      emptyText: "",
    });
  }

  function selectionInsideElement(root, range) {
    if (!root || !range) return false;
    return root.contains(range.commonAncestorContainer);
  }

  function rememberRichTextSelection(el) {
    if (!el || !$(el).hasClass("slide-rich-text-preview")) return;
    lastFocusedRichText = el;
    var selection = window.getSelection ? window.getSelection() : null;
    if (!selection || !selection.rangeCount) return;
    var range = selection.getRangeAt(0);
    if (!selectionInsideElement(el, range)) return;
    savedRichTextRange = range.cloneRange();
  }

  function restoreRichTextSelection() {
    if (!lastFocusedRichText || !savedRichTextRange || !document.body.contains(lastFocusedRichText)) return false;
    if (!selectionInsideElement(lastFocusedRichText, savedRichTextRange)) return false;
    var selection = window.getSelection ? window.getSelection() : null;
    if (!selection) return false;
    try {
      selection.removeAllRanges();
      selection.addRange(savedRichTextRange);
      lastFocusedRichText.focus();
      return true;
    } catch (err) {
      return false;
    }
  }

  function syncSingleRichText($preview) {
    if (!$preview || !$preview.length) return;
    var selector = $preview.data("math-source");
    var $host = mathPreviewScope($preview);
    var $input = $host.find(selector).first();
    if ($input.length) $input.val(serializeRichMathText($preview[0]));
    $preview.data("rich-html", sanitizeRichTextHtml($preview[0]));
  }

  function syncRichTextSources($scope) {
    $scope.find(".slide-rich-text-preview").each(function () {
      syncSingleRichText($(this));
    });
  }

  function mathPreviewScope($element) {
    var $scope = $element.closest("[data-math-row], th, td, .slide-formula-host, .slide-notes-section");
    return $scope.length ? $scope : $("#slideCanvas");
  }

  function updateContentPreview() {
    renderMathText($("#contentPreview"), $("#content").val() || "", {
      emptyText: "暂无内容。",
      displayMode: false,
    });
  }

  function rewriteMarkdownImageLinks(text, assetUrls) {
    var map = assetUrls || {};
    return String(text || "").replace(/(!\[[^\]]*?\]\()([^)]+)(\))/g, function (match, prefix, target, suffix) {
      var url = (function () {
        var normalized = normalizePackageAssetKey(target);
        if (!normalized) return "";
        var candidates = [normalized];
        if (normalized.indexOf("figures/") === 0) {
          candidates.push(normalized.slice("figures/".length));
        }
        if (normalized.indexOf("/") !== -1) {
          candidates.push(normalized.split("/").pop());
        }
        for (var i = 0; i < candidates.length; i++) {
          if (map[candidates[i]]) return map[candidates[i]];
        }
        return "";
      })();
      if (url) return prefix + url + suffix;
      return match;
    });
  }

  function applyMarkdownAssets() {
    var source = rawMarkdownContent || "";
    buildFigurePreviewMap();
    if (!source) {
      updateContentPreview();
      return;
    }
    var rewritten = rewriteMarkdownImageLinks(source, importedPackageAssetUrls);
    $("#content").val(rewritten);
    updateContentPreview();
  }

  function extractPackageImages(assetUrls) {
    var list = [];
    Object.keys(assetUrls || {}).forEach(function (key) {
      if (!/\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(key)) return;
      list.push({
        url: assetUrls[key],
        name: key,
      });
    });
    list.sort(function (a, b) {
      return String(a.name).localeCompare(String(b.name), "zh-Hans-CN");
    });
    return list;
  }

  function renderPackageImages() {
    var $panel = $("#packageImagePanel");
    var $grid = $("#packageImageGrid").empty();
    if (!importedPackageImages.length) {
      $panel.hide();
      $("#btnTogglePackageImages").prop("disabled", true).text("展开图片");
      return;
    }

    importedPackageImages.forEach(function (img, index) {
      $grid.append(
        '<button type="button" class="package-image-item" data-image-index="' + index + '">' +
          '<div class="package-image-number">' + (index + 1) + '</div>' +
          '<img class="package-image-thumb" src="' + escAttr(img.url) + '" alt="' + escAttr(img.name) + '" loading="lazy" />' +
          '<div class="package-image-caption">' + escHtml(img.name) + '</div>' +
        '</button>'
      );
    });

    $("#btnTogglePackageImages")
      .prop("disabled", false)
      .text(packageImagePanelOpen ? "收起图片" : "展开图片");
    $panel.toggle(packageImagePanelOpen);
    if (packageImagePanelOpen) {
      positionPackageImagePanel();
    }
  }

  function positionPackageImagePanel() {
    if (!packageImagePanelOpen || !importedPackageImages.length) return;
    var $panel = $("#packageImagePanel");
    var $button = $("#btnTogglePackageImages");
    if (!$panel.is(":visible") || !$button.length) return;

    var buttonRect = $button[0].getBoundingClientRect();
    var panelWidth = $panel.outerWidth() || 0;
    var panelHeight = $panel.outerHeight() || 0;
    var gap = 12;
    var left = buttonRect.right + gap;
    var top = buttonRect.top;
    var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;

    if (left + panelWidth > viewportWidth - 12) {
      left = Math.max(12, buttonRect.left - panelWidth - gap);
    }
    if (top + panelHeight > viewportHeight - 12) {
      top = Math.max(12, viewportHeight - panelHeight - 12);
    }

    $panel.css({
      left: Math.round(left) + "px",
      top: Math.round(top) + "px",
    });
  }

  function openPackageImageViewer(img, index) {
    if (!img || !img.url) return;
    packageImageViewerOpen = true;
    $("#packageImageViewerImage")
      .attr("src", img.url)
      .attr("alt", img.name || "preview image");
    $("#packageImageViewerCaption").text((Number.isFinite(index) ? (index + 1) + ". " : "") + (img.name || ""));
    $("#packageImageViewer").show();
    $("body").addClass("modal-open");
  }

  function closePackageImageViewer() {
    packageImageViewerOpen = false;
    $("#packageImageViewer").hide();
    $("#packageImageViewerImage").attr("src", "");
    $("#packageImageViewerCaption").text("");
    $("body").removeClass("modal-open");
  }

  function positionFigureHoverPreview($ref) {
    var $panel = $("#figureHoverPreview");
    if (!$panel.is(":visible") || !$ref || !$ref.length) return;

    var rect = $ref[0].getBoundingClientRect();
    var panelWidth = $panel.outerWidth() || 0;
    var panelHeight = $panel.outerHeight() || 0;
    var gap = 12;
    var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    var left = rect.right + gap;
    var top = rect.top - 6;

    if (left + panelWidth > viewportWidth - 12) {
      left = Math.max(12, rect.left - panelWidth - gap);
    }
    if (top + panelHeight > viewportHeight - 12) {
      top = Math.max(12, viewportHeight - panelHeight - 12);
    }

    $panel.css({
      left: Math.round(left) + "px",
      top: Math.round(top) + "px",
    });
  }

  function showFigureHoverPreview($ref) {
    var key = normalizeFigureLabel($ref && $ref.data ? $ref.data("figure-key") : "");
    var figure = figurePreviewMap[key];
    if (!figure || !figure.url) return;

    figureHoverPreviewOpen = true;
    $("#figureHoverPreviewImage")
      .attr("src", figure.url)
      .attr("alt", figure.label || "figure preview");
    $("#figureHoverPreviewLabel").text(figure.label || "");
    $("#figureHoverPreviewCaption").text(figure.caption || figure.label || "");
    $("#figureHoverPreview").show();
    positionFigureHoverPreview($ref);
  }

  function hideFigureHoverPreview() {
    figureHoverPreviewOpen = false;
    $("#figureHoverPreview").hide();
    $("#figureHoverPreviewImage").attr("src", "");
    $("#figureHoverPreviewLabel").text("");
    $("#figureHoverPreviewCaption").text("");
  }

  function setPackageImages(assetUrls) {
    importedPackageAssetUrls = assetUrls || {};
    importedPackageImages = extractPackageImages(importedPackageAssetUrls);
    buildFigurePreviewMap();
    if (!importedPackageImages.length) {
      packageImagePanelOpen = false;
    }
    renderPackageImages();
    applyMarkdownAssets();
    if (slidesData && slidesData.slides) {
      ensureAllSlideFigurePlaceholders(slidesData);
      if (currentSlideIdx >= 0 && slidesData.slides[currentSlideIdx]) {
        renderSlideEditor(slidesData.slides[currentSlideIdx]);
        renderSlideList();
        selectLatexSyncForSlide(currentSlideIdx);
      }
      scheduleLatexSync();
    }
  }

  function updateScopedMathPreviews($scope) {
    $scope.find("[data-math-source]").each(function () {
      var $preview = $(this);
      var selector = $(this).data("math-source");
      var $host = mathPreviewScope($(this));
      var $input = $host.find(selector).first();
      var displayMode = String($preview.data("math-display") || "") === "true";
      if ($preview.hasClass("slide-rich-text-preview") && $preview.is(":focus")) return;
      var richHtml = $preview.data("rich-html");
      if ($preview.hasClass("slide-rich-text-preview") && richHtml) {
        restoreRichTextHtml($preview, richHtml, $input.val() || "");
        return;
      }
      renderMathText($preview, $input.val() || "", {
        displayMode: displayMode ? true : false,
        boxedMath: true,
        emptyText: "暂无内容。",
      });
      if ($input.length) {
        $preview.css({
          color: $input.css("color"),
          fontSize: $input.css("font-size"),
        });
      }
    });
    $scope.find("[data-formula-source]").each(function () {
      var $boxes = $(this);
      var selector = $boxes.data("formula-source");
      var $host = $boxes.closest("[data-math-row], .slide-formula-host, th, td, .slide-notes-section");
      var $input = $host.find(selector).first();
      if (!$input.length) $input = $boxes.prevAll(selector).first();
      renderFormulaBoxes($boxes, $input.val() || "");
    });
  }

  function enterMathEdit($row) {
    if (!$row || !$row.length) return;
    $row.addClass("is-editing");
    var $input = $row.find(".slide-item-input, .slide-textbox-content, .slide-eq-input").first();
    if ($input.length) {
      lastFocusedInput = $input[0];
      lastFocusedTextbox = $input.closest(".slide-textbox")[0] || null;
      setTimeout(function () {
        var input = $input[0];
        if (!input) return;
        try { input.focus({ preventScroll: true }); } catch (err) { input.focus(); }
        if (typeof input.select === "function") input.select();
      }, 0);
    }
  }

  function exitMathEdit($row) {
    if (!$row || !$row.length) return;
    updateScopedMathPreviews($row);
    $row.removeClass("is-editing");
  }

  function setupColumnResize() {
    var $container = $(".container");
    var $input = $(".panel-input");
    var $handle = $("#mainResizeHandle");
    var dragging = false;
    var minLeft = 320;
    var minRight = 500;

    function setLeftWidth(width) {
      if (inputCollapsed) return;
      var total = $container.width() || 0;
      var handleWidth = $handle.outerWidth() || 20;
      var maxLeft = Math.max(minLeft, total - handleWidth - minRight);
      var next = Math.max(minLeft, Math.min(width, maxLeft));
      $input.css("flex-basis", next + "px");
      localStorage.setItem("bg_left_panel_width", String(Math.round(next)));
      refreshEditorSize();
    }

    var savedWidth = parseInt(localStorage.getItem("bg_left_panel_width") || "", 10);
    if (!Number.isNaN(savedWidth)) {
      setLeftWidth(savedWidth);
    }

    $handle.on("mousedown", function (event) {
      if (inputCollapsed || $(event.target).closest("#btnToggleInputPanel").length) return;
      event.preventDefault();
      dragging = true;
      $("body").addClass("resizing-columns");
    });

    $(document).on("mousemove.columnResize", function (event) {
      if (!dragging) return;
      var left = $container.offset().left || 0;
      setLeftWidth(event.pageX - left);
    });

    $(document).on("mouseup.columnResize", function () {
      if (!dragging) return;
      dragging = false;
      $("body").removeClass("resizing-columns");
      refreshEditorSize();
    });

    $(window).on("resize.columnResize", function () {
      if (inputCollapsed) return;
      var current = $input.outerWidth() || minLeft;
      setLeftWidth(current);
    });
  }

  function applyLectureSource(title, content) {
    $("#content").val(content || "");
    updateContentPreview();
    if (title) {
      $("#customRequirements").val("Title: " + title);
    }
  }

  function applyImportedMarkdownSource(data) {
    var files = data.files || [];
    var content = data.content || "";
    var title = data.filename || (files[0] || "knowledge_graph");
    $("#content").val(content);
    updateContentPreview();
    if (title) {
      $("#customRequirements").val("Title: " + title.replace(/\.(zip|md|markdown|txt)$/i, ""));
    }
    setStatus("Imported " + files.length + " file(s), " + (data.char_count || content.length) + " chars", "success");
  }

  function buildProjectSavePayload() {
    if (!slidesData) return null;
    saveCurrentSlide();
    syncLatexFromSlides();
    ensureAllSlideFigurePlaceholders(slidesData);
    var enteredTitle = ($("#pptChapterTitleInput").val() || "").trim();
    var chapterTitle = enteredTitle || slidesData.chapter_title || slidesData.title || "未命名章节";
    slidesData.chapter_title = chapterTitle;
    return {
      chapter_id: String(enteredTitle || slidesData.chapter_id || slidesData.id || slidesData.title || "presentation"),
      chapter_title: String(chapterTitle),
      title: enteredTitle || slidesData.title,
      subtitle: slidesData.subtitle,
      author: slidesData.author,
      date: slidesData.date,
      slides: slidesData.slides,
      figure_assets: buildFigureAssetPayload(),
      latex: fullLatex || "",
    };
  }

  function renderSavedPptProjects() {
    var $chapter = $("#savedPptChapterSelect");
    var $slide = $("#savedPptSlideSelect");
    $chapter.empty().append('<option value="">选择章节</option>');
    for (var i = 0; i < savedPptProjects.length; i++) {
      var project = savedPptProjects[i] || {};
      var label = project.chapter_title || project.title || project.chapter_id || ("章节 " + (i + 1));
      $chapter.append('<option value="' + i + '">' + escHtml(label) + '</option>');
    }
    $slide.empty().append('<option value="">选择页面</option>').prop("disabled", true);
    $("#btnLoadSavedSlide").prop("disabled", true);
    $("#savedPptSlideGallery").empty().hide();
  }

  function loadSavedPptProjects() {
    $("#btnRefreshSavedPpt").prop("disabled", true).text("读取中...");
    return fetch("/beamer-generator/api/saved-projects", { headers: { "Accept": "application/json" } })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        savedPptProjects = Array.isArray(data.projects) ? data.projects : [];
        renderSavedPptProjects();
        setStatus("已读取保存内容，共 " + savedPptProjects.length + " 个章节", "success");
      })
      .catch(function (err) {
        savedPptProjects = [];
        renderSavedPptProjects();
        setStatus("读取保存内容失败: " + err.message, "error");
      })
      .finally(function () {
        $("#btnRefreshSavedPpt").prop("disabled", false).text("查找已保存内容");
      });
  }

  function savedPptProjectData(projectIndex) {
    var project = savedPptProjects[projectIndex];
    if (!project || !project.chapter_id) return Promise.reject(new Error("未选择保存章节"));
    if (project.fullData && Array.isArray(project.fullData.slides)) return Promise.resolve(project.fullData);
    return fetch("/beamer-generator/api/saved-projects/" + encodeURIComponent(project.chapter_id), {
      headers: { "Accept": "application/json" },
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        project.fullData = data || {};
        project.slides = Array.isArray(project.fullData.slides)
          ? project.fullData.slides.map(function (slide, idx) {
              return {
                page_index: idx,
                title: (slide || {}).title || ("页面 " + (idx + 1)),
                type: (slide || {}).type || "content",
              };
            })
          : project.slides;
        return project.fullData;
      });
  }

  function renderSavedSlideMini(slide, pageIndex, className) {
    slide = slide || {};
    var items = Array.isArray(slide.items) ? slide.items.slice(0, 4) : [];
    var equations = Array.isArray(slide.equations) ? slide.equations.slice(0, 2) : [];
    var callouts = Array.isArray(slide.callouts) ? slide.callouts.slice(0, 3) : [];
    var images = [];
    (slide.images || []).forEach(function (img) {
      var url = (img && (img.url || img.path || img.src)) || "";
      if (url) images.push(url);
    });
    (slide.placeholders || []).forEach(function (ph) {
      var url = (ph && (ph.asset || ph.url || ph.path)) || "";
      if (url) images.push(url);
    });
    var html = '<div class="saved-slide-mini ' + (slide.reviewBackground ? "review-background " : "") + (className || "") + '">' +
      '<div class="saved-slide-mini-page">第 ' + (pageIndex + 1) + ' 页</div>' +
      '<div class="saved-slide-mini-title">' + escHtml(slide.title || "未命名页面") + '</div>' +
      '<div class="saved-slide-mini-body">';
    if (images.length) {
      html += '<div class="saved-slide-mini-images">';
      images.slice(0, 2).forEach(function (url) {
        html += '<img src="' + escAttr(url) + '" alt="" />';
      });
      html += '</div>';
    }
    if (items.length) {
      html += '<ul>';
      items.forEach(function (item) {
        html += '<li>' + escHtml(String(item || "").replace(/\s+/g, " ").slice(0, 80)) + '</li>';
      });
      html += '</ul>';
    }
    if (equations.length) {
      html += '<div class="saved-slide-mini-equations">';
      equations.forEach(function (eq) {
        html += '<div class="saved-slide-mini-equation" data-math-source="' + escAttr(String(eq || "")) + '">' +
          escHtml(String(eq || "").slice(0, 80)) + '</div>';
      });
      html += '</div>';
    }
    callouts.forEach(function (callout) {
      callout = callout || {};
      var x = Math.max(0, Math.min(100, (Number(callout.x) || 130) / SLIDE_DESIGN_WIDTH * 100));
      var y = Math.max(0, Math.min(100, (Number(callout.y) || 178) / SLIDE_DESIGN_HEIGHT * 100));
      var w = Math.max(14, Math.min(70, (Number(callout.width) || 250) / SLIDE_DESIGN_WIDTH * 100));
      var h = Math.max(8, Math.min(35, (Number(callout.height) || 92) / SLIDE_DESIGN_HEIGHT * 100));
      html += '<div class="saved-slide-mini-callout" style="left:' + x.toFixed(2) + '%;top:' + y.toFixed(2) + '%;width:' + w.toFixed(2) + '%;height:' + h.toFixed(2) + '%;">' +
        escHtml(String(callout.text || "").slice(0, 40)) + '</div>';
    });
    if (!images.length && !items.length && !equations.length && !callouts.length) {
      html += '<div class="saved-slide-mini-empty">空白页</div>';
    }
    html += '</div></div>';
    return html;
  }

  function renderSavedSlideMiniMath($root) {
    if (!$root || !$root.length) return;
    $root.find(".saved-slide-mini-equation").each(function () {
      var $eq = $(this);
      var source = $eq.data("math-source") || $eq.text() || "";
      renderMathText($eq, source, {
        displayMode: true,
        boxedMath: false,
        emptyText: source,
      });
    });
  }

  function renderSavedPptGalleryShell($gallery, title) {
    $gallery.empty().append(
      '<div class="saved-ppt-gallery-header">' +
        '<div class="saved-ppt-gallery-title-wrap">' +
          '<span class="saved-ppt-gallery-title">' + escHtml(title || "已保存章节页面") + '</span>' +
          '<span class="saved-ppt-gallery-hint">按住缩略图拖到当前 PPT 左侧列表，即可插入到本章节</span>' +
        '</div>' +
        '<button type="button" class="saved-ppt-gallery-close" data-action="close-saved-ppt-gallery" title="关闭">×</button>' +
      '</div>' +
      '<div class="saved-ppt-gallery-content"></div>'
    );
    return $gallery.find(".saved-ppt-gallery-content");
  }

  function showSavedPptGalleryMessage(message, title) {
    var $gallery = $("#savedPptSlideGallery").show();
    var $content = renderSavedPptGalleryShell($gallery, title);
    $content.html('<div class="saved-ppt-gallery-empty">' + escHtml(message) + '</div>');
    positionSavedPptGallery();
  }

  function renderSavedPptGallery(projectIndex, projectData) {
    var project = savedPptProjects[projectIndex] || {};
    var title = projectData && (projectData.chapter_title || projectData.title || projectData.chapter_id);
    title = title || project.chapter_title || project.title || project.chapter_id || "已保存章节页面";
    var $gallery = $("#savedPptSlideGallery").show();
    var $content = renderSavedPptGalleryShell($gallery, title);
    var slides = projectData && Array.isArray(projectData.slides) ? projectData.slides : [];
    if (!slides.length) {
      $content.html('<div class="saved-ppt-gallery-empty">该章节暂无页面</div>');
      positionSavedPptGallery();
      return;
    }
    slides.forEach(function (slide, idx) {
      var $card = $(
        '<button type="button" class="saved-ppt-slide-card" draggable="true" data-page-index="' + idx + '">' +
          renderSavedSlideMini(slide, idx, "") +
        '</button>'
      );
      renderSavedSlideMiniMath($card);
      $card.on("click", function () {
        openSavedSlidePreview(slide, idx);
      });
      $card.on("dragstart", function (e) {
        savedSlideDragPayload = { projectIndex: projectIndex, pageIndex: idx };
        if (e.originalEvent && e.originalEvent.dataTransfer) {
          e.originalEvent.dataTransfer.effectAllowed = "copy";
          e.originalEvent.dataTransfer.setData("text/plain", JSON.stringify(savedSlideDragPayload));
        }
      });
      $card.on("dragend", function () {
        savedSlideDragPayload = null;
        $(".slide-insert-dropzone").removeClass("active");
      });
      $content.append($card);
    });
    positionSavedPptGallery();
  }

  function savedPptGalleryDragBounds($gallery) {
    var margin = 12;
    var editor = $("#viewPpt:visible .ppt-editor")[0] || $("#viewPpt:visible")[0];
    var editorRect = editor ? editor.getBoundingClientRect() : null;
    var width = $gallery.outerWidth() || 360;
    var height = $gallery.outerHeight() || 148;
    var maxLeft = Math.max(margin, window.innerWidth - width - margin);
    var bottomLimit = editorRect ? editorRect.top - margin : window.innerHeight - margin;
    var maxTop = Math.max(margin, bottomLimit - height);
    return { margin: margin, maxLeft: maxLeft, maxTop: maxTop };
  }

  function clampSavedPptGalleryPosition(left, top) {
    var $gallery = $("#savedPptSlideGallery");
    var bounds = savedPptGalleryDragBounds($gallery);
    return {
      left: Math.min(Math.max(bounds.margin, left), bounds.maxLeft),
      top: Math.min(Math.max(bounds.margin, top), bounds.maxTop),
    };
  }

  function positionSavedPptGallery() {
    var $gallery = $("#savedPptSlideGallery");
    if (!$gallery.length || !$gallery.is(":visible") || !$gallery.children().length) return;
    var anchor = $("#btnSaveProject")[0] || $("#savedPptChapterSelect")[0];
    if (!anchor) return;
    var rect = anchor.getBoundingClientRect();
    var editor = $("#viewPpt:visible .ppt-editor")[0] || $("#viewPpt:visible")[0];
    var editorRect = editor ? editor.getBoundingClientRect() : null;
    var margin = 12;
    var width = Math.min(920, window.innerWidth - margin * 2);
    width = Math.max(360, width);
    var left = Math.min(Math.max(margin, rect.right - width), window.innerWidth - width - margin);
    $gallery.css({ left: left + "px", width: width + "px", maxHeight: "" });
    var galleryHeight = $gallery.outerHeight() || 148;
    var topLimit = editorRect ? editorRect.top - margin : rect.top - margin;
    var availableHeight = Math.max(96, topLimit - margin);
    if (galleryHeight > availableHeight) {
      $gallery.css("max-height", availableHeight + "px");
      galleryHeight = $gallery.outerHeight() || availableHeight;
    }
    if (savedPptGalleryManualPosition) {
      var manual = clampSavedPptGalleryPosition(savedPptGalleryManualPosition.left, savedPptGalleryManualPosition.top);
      savedPptGalleryManualPosition = manual;
      $gallery.css({ left: manual.left + "px", top: manual.top + "px" });
      return;
    }
    var top = editorRect ? editorRect.top - galleryHeight - margin : rect.top - galleryHeight - margin;
    if (top < margin) top = margin;
    $gallery.css({ top: top + "px" });
  }

  function openSavedSlidePreview(slide, pageIndex) {
    var $content = $("#savedSlidePreviewContent");
    $content.html(renderSavedSlideMini(slide, pageIndex, "saved-slide-mini-large"));
    renderSavedSlideMiniMath($content);
    $("#savedSlidePreviewModal").show();
    $("body").addClass("modal-open");
  }

  function closeSavedSlidePreview() {
    $("#savedSlidePreviewModal").hide();
    $("#savedSlidePreviewContent").empty();
    $("body").removeClass("modal-open");
  }

  function renderSavedPptSlides(projectIndex) {
    var $slide = $("#savedPptSlideSelect");
    $slide.empty().append('<option value="">选择页面</option>');
    var project = savedPptProjects[projectIndex];
    if (!project || !Array.isArray(project.slides) || !project.slides.length) {
      $slide.prop("disabled", true);
      $("#btnLoadSavedSlide").prop("disabled", true);
      $("#savedPptSlideGallery").empty().hide();
      return;
    }
    project.slides.forEach(function (slide) {
      var label = slide.title || ("页面 " + (slide.page_index + 1));
      $slide.append('<option value="' + slide.page_index + '">' + escHtml((slide.page_index + 1) + ". " + label) + '</option>');
    });
    $slide.prop("disabled", false);
    $("#btnLoadSavedSlide").prop("disabled", false);
  }

  function loadSavedSlideFromProject(projectIndex, pageIndex) {
    return savedPptProjectData(projectIndex).then(function (projectData) {
      var slides = Array.isArray(projectData.slides) ? projectData.slides : [];
      if (pageIndex < 0 || pageIndex >= slides.length) throw new Error("未找到页面内容");
      return slides[pageIndex];
    });
  }

  function insertSavedSlideIntoCurrentProject(slideData, insertIndex) {
    if (!slidesData || !slideData) return;
    if (!Array.isArray(slidesData.slides)) slidesData.slides = [];
    saveCurrentSlide();
    var slide = deepClone(slideData);
    if (!slide.images) slide.images = [];
    if (!slide.textboxes) slide.textboxes = [];
    if (!slide.callouts) slide.callouts = [];
    slide.placeholders = normalizePlaceholders(slide.placeholders);
    if (slide.table) slide.table = normalizeTable(slide.table);
    var targetIndex = insertIndex;
    if (typeof targetIndex !== "number" || isNaN(targetIndex)) targetIndex = currentSlideIdx + 1;
    targetIndex = Math.max(0, Math.min(slidesData.slides.length, targetIndex));
    slidesData.slides.splice(targetIndex, 0, slide);
    for (var i = 0; i < slidesData.slides.length; i++) {
      slidesData.slides[i].id = i;
    }
    currentSlideIdx = targetIndex;
    renderSlideList();
    renderSlideEditor(slidesData.slides[targetIndex]);
    selectLatexSyncForSlide(targetIndex);
    syncLatexFromSlides();
    scheduleLatexSync();
    commitHistorySnapshot(false);
    setStatus("已插入保存页面", "success");
  }

  function replaceCurrentSlideWithSaved(slideData) {
    if (!slidesData || currentSlideIdx < 0 || !slideData) return;
    saveCurrentSlide();
    var slide = deepClone(slideData);
    if (!slide.images) slide.images = [];
    if (!slide.textboxes) slide.textboxes = [];
    if (!slide.callouts) slide.callouts = [];
    slide.placeholders = normalizePlaceholders(slide.placeholders);
    if (slide.table) slide.table = normalizeTable(slide.table);
    slidesData.slides[currentSlideIdx] = slide;
    renderSlideEditor(slide);
    renderSlideList();
    selectSlide(currentSlideIdx);
    syncLatexFromSlides();
    scheduleLatexSync();
    setStatus("已替换当前页面", "success");
  }

  function renderSavedLectureOptions() {
    var $select = $("#savedLectureSelect");
    $select.empty();
    if (!savedLectureChapters.length) {
      $select.append('<option value="">暂无已保存授课文稿</option>');
      return;
    }
    $select.append('<option value="">选择已保存章节文稿...</option>');
    for (var i = 0; i < savedLectureChapters.length; i++) {
      var chapter = savedLectureChapters[i];
      var title = chapter.title || chapter.id || ("章节 " + (i + 1));
      $select.append(
        '<option value="' + i + '">' + escHtml(title) + '</option>'
      );
    }
  }

  function loadSavedLectureChapters() {
    var $select = $("#savedLectureSelect");
    $select.prop("disabled", true).html('<option value="">正在读取已保存章节...</option>');
    return fetch("/api/education/list-chapters", { headers: { "Accept": "application/json" } })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        var chapters = Array.isArray(data.chapters) ? data.chapters : [];
        savedLectureChapters = chapters.filter(function (chapter) {
          return chapter && String(chapter.lecture_content || "").trim();
        });
        renderSavedLectureOptions();
      })
      .catch(function () {
        savedLectureChapters = [];
        $select.html('<option value="">读取已保存章节失败</option>');
      })
      .finally(function () {
        $select.prop("disabled", false);
      });
  }

  function setStatus(msg, type) {
    var $s = $("#status");
    if (type === "info" && isGenerating) {
      var progress = Math.max(0, Math.min(100, Math.round(latexGenerateProgress || 0)));
      $s.attr("class", "status info").html(
        msg +
        '<div class="progress-row">' +
          '<div class="progress-bar"><div class="progress-fill" style="width:' + progress + '%"></div></div>' +
          '<span class="progress-percent">' + progress + '%</span>' +
        '</div>'
      );
    } else {
      $s.attr("class", "status " + (type || "")).text(msg);
    }
  }

  function updateLatexGenerateProgress(value, msg) {
    latexGenerateProgress = Math.max(0, Math.min(100, Number(value) || 0));
    if (msg) setStatus(msg, "info");
  }

  function updateDownloadPptxButton() {
    $("#btnDownloadPptx").prop("disabled", !slidesData || !slidesData.slides || !slidesData.slides.length);
  }

  function setGenerating(state) {
    isGenerating = state;
    if (state) latexGenerateProgress = 0;
    $("#btnGenerate").prop("disabled", state)
      .text(state ? "生成中..." : "生成演示文稿");
    if (!state) {
      var has = !!fullLatex;
      $("#btnCopy, #btnDownloadTex, #btnConvertPpt").prop("disabled", !has);
      updateDownloadPptxButton();
      updateHistoryButtons();
    } else {
      $("#btnCopy, #btnDownloadTex, #btnConvertPpt, #btnDownloadPptx").prop("disabled", true);
      $("#btnUndoPpt, #btnRedoPpt").prop("disabled", true);
    }
  }

  $("#savedLectureSelect").on("change", function () {
    var index = parseInt($(this).val(), 10);
    if (Number.isNaN(index) || !savedLectureChapters[index]) {
      return;
    }
    var chapter = savedLectureChapters[index];
    applyLectureSource(chapter.title || chapter.id || "", chapter.lecture_content || "");
    setStatus("已加载章节：" + (chapter.title || chapter.id || ""), "success");
  });

  $("#btnRefreshSavedLectures").on("click", function () {
    loadSavedLectureChapters();
  });

  $("#btnRefreshSavedPpt").on("click", function () {
    loadSavedPptProjects();
  });

  $("#savedPptChapterSelect").on("change", function () {
    var index = parseInt($(this).val(), 10);
    if (Number.isNaN(index) || !savedPptProjects[index]) {
      $("#savedPptSlideSelect").empty().append('<option value="">选择页面</option>').prop("disabled", true);
      $("#btnLoadSavedSlide").prop("disabled", true);
      $("#savedPptSlideGallery").empty().hide();
      return;
    }
    renderSavedPptSlides(index);
    showSavedPptGalleryMessage("正在加载页面...", "已保存章节页面");
    savedPptProjectData(index)
      .then(function (projectData) {
        renderSavedPptSlides(index);
        renderSavedPptGallery(index, projectData);
      })
      .catch(function (err) {
        showSavedPptGalleryMessage("加载页面失败：" + err.message, "已保存章节页面");
      });
  });

  $("#btnLoadSavedSlide").on("click", function () {
    var chapterIndex = parseInt($("#savedPptChapterSelect").val(), 10);
    var slideIndex = parseInt($("#savedPptSlideSelect").val(), 10);
    if (Number.isNaN(chapterIndex) || Number.isNaN(slideIndex)) return;
    var project = savedPptProjects[chapterIndex];
    if (!project || !project.chapter_id) return;
    var $button = $(this);
    $button.prop("disabled", true).text("读取中...");
    loadSavedSlideFromProject(chapterIndex, slideIndex)
      .then(function (slide) {
        if (!slidesData) throw new Error("当前没有可编辑的 PPT");
        replaceCurrentSlideWithSaved(slide);
      })
      .catch(function (err) {
        setStatus("调用保存页面失败: " + err.message, "error");
      })
      .finally(function () {
        $button.prop("disabled", false).text("调用此页");
      });
  });

  $("#savedSlidePreviewModal").on("click", "[data-action='close-saved-slide-preview']", function () {
    closeSavedSlidePreview();
  });

  $("#savedPptSlideGallery").on("click", "[data-action='close-saved-ppt-gallery']", function (e) {
    e.preventDefault();
    e.stopPropagation();
    $("#savedPptSlideGallery").hide();
  });

  $("#savedPptSlideGallery").on("mousedown", function (e) {
    if (e.button !== 0) return;
    var $target = $(e.target);
    if ($target.closest(".saved-ppt-slide-card, .saved-ppt-gallery-close, button, select, input, textarea, a").length) return;
    if (!$target.closest(".saved-ppt-gallery-header, .saved-ppt-gallery-content, .saved-ppt-gallery-empty").length && e.target !== this) return;

    e.preventDefault();
    var $gallery = $(this);
    var startX = e.clientX;
    var startY = e.clientY;
    var startLeft = parseFloat($gallery.css("left")) || 0;
    var startTop = parseFloat($gallery.css("top")) || 0;
    $("body").addClass("moving-saved-ppt-gallery");

    $(document).on("mousemove.savedPptGalleryMove", function (moveEvent) {
      var next = clampSavedPptGalleryPosition(startLeft + moveEvent.clientX - startX, startTop + moveEvent.clientY - startY);
      savedPptGalleryManualPosition = next;
      $gallery.css({ left: next.left + "px", top: next.top + "px" });
    });

    $(document).on("mouseup.savedPptGalleryMove", function () {
      $("body").removeClass("moving-saved-ppt-gallery");
      $(document).off("mousemove.savedPptGalleryMove mouseup.savedPptGalleryMove");
    });
  });

  $(window).on("resize.savedPptGallery scroll.savedPptGallery", positionSavedPptGallery);

  $("#slideCanvas, .ppt-editor").on("dragover", function (e) {
    if (!savedSlideDragPayload) return;
    if ($(e.target).closest("#slideList").length) return;
    e.preventDefault();
    if (e.originalEvent && e.originalEvent.dataTransfer) {
      e.originalEvent.dataTransfer.dropEffect = "copy";
    }
  });

  $("#slideCanvas, .ppt-editor").on("drop", function (e) {
    if (!savedSlideDragPayload) return;
    if ($(e.target).closest("#slideList").length) return;
    e.preventDefault();
    var payload = savedSlideDragPayload;
    savedSlideDragPayload = null;
    loadSavedSlideFromProject(payload.projectIndex, payload.pageIndex)
      .then(function (slide) {
        if (!slidesData) throw new Error("当前没有可编辑的 PPT");
        insertSavedSlideIntoCurrentProject(slide);
      })
      .catch(function (err) {
        setStatus("拖拽插入失败: " + err.message, "error");
      });
  });

  $("#btnImportMarkdown").on("click", function () {
    $("#markdownImporter").val("").trigger("click");
  });

  $("#btnImportGraphPackage").on("click", function () {
    $("#graphPackageImporter").val("").trigger("click");
  });

  $("#btnTogglePackageImages").on("click", function () {
    if (!importedPackageImages.length) return;
    packageImagePanelOpen = !packageImagePanelOpen;
    renderPackageImages();
  });

  $("#packageImagePanel").on("click", "[data-action='close-package-image-panel']", function (e) {
    e.preventDefault();
    packageImagePanelOpen = false;
    renderPackageImages();
  });

  $("#packageImageGrid").on("click", ".package-image-item", function () {
    var index = parseInt($(this).data("image-index"), 10);
    if (Number.isNaN(index) || !importedPackageImages[index]) return;
    openPackageImageViewer(importedPackageImages[index], index);
  });

  $("#packageImageViewer").on("click", function (e) {
    if ($(e.target).is("#packageImageViewer") || $(e.target).closest("[data-action='close-package-image-viewer']").length) {
      closePackageImageViewer();
    }
  });

  $(document).on("keydown.packageImageViewer", function (e) {
    if (e.key === "Escape" && packageImageViewerOpen) {
      closePackageImageViewer();
    }
  });

  $(window).on("resize.packageImagePanel scroll.packageImagePanel", function () {
    if (packageImagePanelOpen) {
      positionPackageImagePanel();
    }
  });

  $(window).on("resize.figureHoverPreview scroll.figureHoverPreview", function () {
    if (figureHoverPreviewOpen) {
      var $ref = $("#contentPreview .figure-ref.has-figure-preview:hover").first();
      if ($ref.length) {
        positionFigureHoverPreview($ref);
      } else {
        hideFigureHoverPreview();
      }
    }
  });

  $("#markdownImporter").on("change", function () {
    var file = this.files[0];
    if (!file) return;

    var formData = new FormData();
    formData.append("file", file);
    $("#btnImportMarkdown").prop("disabled", true).text("导入中...");
    setStatus("正在导入知识图谱文件...", "info");

    $.ajax({
      url: "/beamer-generator/api/import-markdown-source",
      method: "POST",
      data: formData,
      processData: false,
      contentType: false,
      success: function (data) {
        if (data.error) {
          setStatus("导入失败: " + data.error, "error");
          return;
        }
        var content = data.content || "";
        var title = data.filename || file.name || "知识图谱";
        rawMarkdownContent = content;
        applyMarkdownAssets();
        $("#customRequirements").val("Title: " + title.replace(/\.(md|markdown|zip|txt)$/i, ""));
        setStatus("已导入 Markdown 知识图谱，共 " + (data.char_count || content.length) + " 字符", "success");
      },
      error: function (xhr) {
        var msg = "请求失败";
        if (xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
        setStatus("导入请求失败: " + msg, "error");
      },
      complete: function () {
        $("#btnImportMarkdown").prop("disabled", false).text("导入 MD 知识图谱");
      },
    });
  });

  $("#graphPackageImporter").on("change", function () {
    var files = Array.prototype.slice.call(this.files || []);
    if (!files.length) return;

    var imageFiles = files.filter(function (file) {
      return /\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(file.name || "");
    });
    if (!imageFiles.length) {
      setStatus("请选择包含图片的图片包文件夹", "error");
      return;
    }

    var formData = new FormData();
    imageFiles.forEach(function (file) {
      var relPath = file.webkitRelativePath || file.name;
      formData.append("files", file, relPath);
    });

    $("#btnImportGraphPackage").prop("disabled", true).text("上传中...");
    setStatus("正在上传图片包...", "info");

    $.ajax({
      url: "/beamer-generator/api/import-image-package",
      method: "POST",
      data: formData,
      processData: false,
      contentType: false,
      success: function (data) {
        if (data.error) {
          setStatus("图片包上传失败: " + data.error, "error");
          return;
        }
        setPackageImages((data.result && data.result.asset_urls) || {});
        packageImagePanelOpen = false;
        renderPackageImages();
        setStatus("图片包上传完成，共 " + imageFiles.length + " 张图片", "success");
      },
      error: function (xhr) {
        var msg = "请检查图片包格式";
        if (xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
        setStatus("图片包上传失败: " + msg, "error");
      },
      complete: function () {
        $("#btnImportGraphPackage").prop("disabled", false).text("上传图片包");
      },
    });
  });

  $("#content").on("input", updateContentPreview);
  $("#contentPreview").on("mouseenter", ".figure-ref.has-figure-preview", function () {
    showFigureHoverPreview($(this));
  });
  $("#contentPreview").on("mousemove", ".figure-ref.has-figure-preview", function () {
    if (figureHoverPreviewOpen) {
      positionFigureHoverPreview($(this));
    }
  });
  $("#contentPreview").on("mouseleave", ".figure-ref.has-figure-preview", function () {
    hideFigureHoverPreview();
  });

  editor.on("cursorActivity", scheduleLatexSelectionSync);
  editor.on("change", scheduleLatexManualSync);

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function downloadFile(content, filename, mime) {
    var blob = (typeof content === "string")
      ? new Blob([content], { type: mime + ";charset=utf-8" })
      : new Blob([content], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function escHtml(s) {
    return $("<span>").text(s || "").html();
  }

  function escAttr(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeLatexText(text) {
    return String(text == null ? "" : text)
      .replace(/\\/g, "\\textbackslash{}")
      .replace(/&/g, "\\&")
      .replace(/%/g, "\\%")
      .replace(/\$/g, "\\$")
      .replace(/#/g, "\\#")
      .replace(/_/g, "\\_")
      .replace(/\{/g, "\\{")
      .replace(/\}/g, "\\}")
      .replace(/~/g, "\\textasciitilde{}")
      .replace(/\^/g, "\\textasciicircum{}")
      .replace(/\r?\n/g, " ");
  }

  function repairPptLatexArtifacts(text) {
    var s = String(text == null ? "" : text);
    if (!s) return "";
    if (s.indexOf("textbackslash") !== -1 || /\\[$_{}]/.test(s)) {
      s = s
        .replace(/\\textbackslash\\?\{\\?\}/g, "\\")
        .replace(/\\\$/g, "$")
        .replace(/\\_/g, "_")
        .replace(/\\\{/g, "{")
        .replace(/\\\}/g, "}");
    }
    return s;
  }

  function escapeLatexTextPreservingMath(text) {
    var source = repairPptLatexArtifacts(text);
    var out = "";
    var pattern = /\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|\$\$([\s\S]*?)\$\$|(^|[^\\])\$([^$\n]+?)\$/g;
    var lastIndex = 0;
    var match;
    while ((match = pattern.exec(source)) !== null) {
      var prefix = match[4] || "";
      var matchStart = match.index + prefix.length;
      out += escapeLatexText(source.slice(lastIndex, matchStart));
      out += source.slice(matchStart, pattern.lastIndex);
      lastIndex = pattern.lastIndex;
    }
    out += escapeLatexText(source.slice(lastIndex));
    return out;
  }

  function normalizeSlideEditableText(slide) {
    if (!slide) return;
    slide.title = repairPptLatexArtifacts(slide.title || "");
    slide.subtitle = repairPptLatexArtifacts(slide.subtitle || "");
    slide.notes = repairPptLatexArtifacts(slide.notes || "");
    if (Array.isArray(slide.items)) {
      slide.items = slide.items.map(function (item) { return repairPptLatexArtifacts(item); });
    }
    if (slide.table) {
      if (Array.isArray(slide.table.headers)) {
        slide.table.headers = slide.table.headers.map(function (h) { return repairPptLatexArtifacts(h); });
      }
      if (Array.isArray(slide.table.rows)) {
        slide.table.rows = slide.table.rows.map(function (row) {
          return Array.isArray(row) ? row.map(function (cell) { return repairPptLatexArtifacts(cell); }) : row;
        });
      }
    }
    if (Array.isArray(slide.textboxes)) {
      slide.textboxes.forEach(function (tb) {
        if (tb) tb.text = repairPptLatexArtifacts(tb.text || "");
      });
    }
    if (!Array.isArray(slide.callouts)) slide.callouts = [];
    slide.callouts.forEach(function (callout) {
      if (callout) callout.text = repairPptLatexArtifacts(callout.text || "");
    });
  }

  function syncKey(slideIdx, part, a, b) {
    var key = "s" + slideIdx + ":" + part;
    if (a !== undefined && a !== null) key += ":" + a;
    if (b !== undefined && b !== null) key += ":" + b;
    return key;
  }

  function clearLatexSyncMarks() {
    for (var i = 0; i < latexSyncMarks.length; i++) {
      latexSyncMarks[i].clear();
    }
    latexSyncMarks = [];
  }

  function clearPptSyncHighlights() {
    $("#slideCanvas").find(".sync-highlight").removeClass("sync-highlight");
    if (pptSyncHighlightTimer) {
      clearTimeout(pptSyncHighlightTimer);
      pptSyncHighlightTimer = null;
    }
  }

  function runWithSyncSelectionLock(fn) {
    syncSelectionLock = true;
    try {
      fn();
    } finally {
      setTimeout(function () {
        syncSelectionLock = false;
      }, 0);
    }
  }

  function selectLatexSyncRange(key) {
    clearLatexSyncMarks();
    var range = latexSyncMap[key];
    if (!range || !editor || !editor.posFromIndex) return;
    var from = editor.posFromIndex(range.start);
    var to = editor.posFromIndex(range.end);
    runWithSyncSelectionLock(function () {
      var hadEditorFocus = $(".CodeMirror").hasClass("CodeMirror-focused");
      if (hadEditorFocus) {
        if (editor.setSelection) {
          editor.setSelection(from, to);
        } else if (editor.setCursor) {
          editor.setCursor(from);
        }
      }
      if (editor.scrollIntoView) {
        editor.scrollIntoView({ from: from, to: to }, 80);
      }
    });
    latexSyncMarks.push(editor.markText(from, to, { className: "latex-sync-highlight" }));
  }

  function selectLatexSyncForSlide(slideIdx) {
    if (!slidesData || !slidesData.slides || slideIdx < 0 || slideIdx >= slidesData.slides.length) return;
    var preferredKeys = [
      syncKey(slideIdx, "frame"),
      syncKey(slideIdx, "title"),
      syncKey(slideIdx, "subtitle"),
      syncKey(slideIdx, "item", 0),
      syncKey(slideIdx, "equation", 0),
      syncKey(slideIdx, "placeholder", 0),
      syncKey(slideIdx, "textbox", 0),
      syncKey(slideIdx, "notes"),
    ];
    for (var i = 0; i < preferredKeys.length; i++) {
      if (latexSyncMap[preferredKeys[i]]) {
        selectLatexSyncRange(preferredKeys[i]);
        return;
      }
    }
  }

  function focusAndSelectElement($el) {
    if (!$el || !$el.length) return;
    var el = $el[0];
    if (!el) return;

    var $mathRow = $el.closest("[data-math-row]");
    if ($mathRow.length) {
      $mathRow.addClass("is-editing");
    }

    if (typeof el.focus === "function") {
      try { el.focus({ preventScroll: true }); } catch (err) { el.focus(); }
    }

    if (typeof el.select === "function") {
      try { el.select(); } catch (err2) {}
      return;
    }

    if (typeof el.setSelectionRange === "function" && typeof el.value === "string") {
      try { el.setSelectionRange(0, el.value.length); } catch (err3) {}
    }
  }

  function selectPptSyncTarget(key) {
    clearPptSyncHighlights();
    var range = latexSyncMap[key];
    if (range && slidesData && slidesData.slides && range.slideIdx !== undefined &&
        range.slideIdx !== currentSlideIdx && range.slideIdx >= 0 && range.slideIdx < slidesData.slides.length) {
      saveCurrentSlide();
      currentSlideIdx = range.slideIdx;
      $(".slide-thumb").removeClass("active").eq(currentSlideIdx).addClass("active");
      renderSlideEditor(slidesData.slides[currentSlideIdx]);
    }
    var $target = $('#slideCanvas [data-sync-key="' + key + '"]').first();
    if (!$target.length && /:frame$/.test(key)) {
      $target = $("#slideCanvas .slide-render").first();
    }
    if (!$target.length) return;

    var $highlight = $target;
    var $selectionTarget = $target;
    var $mathRow = $target.closest("[data-math-row]");
    var $editableWithKey = $(
      '#slideCanvas input[data-sync-key="' + key + '"], ' +
      '#slideCanvas textarea[data-sync-key="' + key + '"]'
    ).first();
    if (!$target.is("input, textarea") && $editableWithKey.length) {
      $selectionTarget = $editableWithKey;
      $mathRow = $editableWithKey.closest("[data-math-row]");
      if ($mathRow.length) {
        $highlight = $mathRow;
      } else if ($target.is(".slide-image-placeholder, .slide-textbox")) {
        $highlight = $target;
      } else {
        $highlight = $editableWithKey;
      }
    }

    if ($target.hasClass("slide-hidden-math-source")) {
      $highlight = $mathRow.find(".slide-math-preview").first();
      if ($highlight.length) {
        $selectionTarget = $mathRow.find(".slide-hidden-math-source").first();
      }
    } else if ($target.is(".slide-math-preview")) {
      $highlight = $target;
      $selectionTarget = $mathRow.find(".slide-hidden-math-source").first();
    } else if ($target.is("[data-th], [data-tr], [data-field='title'], [data-field='subtitle'], [data-field='notes'], .slide-placeholder-label, .slide-item-input, .slide-eq-input, .slide-textbox-content")) {
      $selectionTarget = $target;
    }

    if ($mathRow.length && ($target.hasClass("slide-hidden-math-source") || $target.is(".slide-math-preview"))) {
      $highlight = $mathRow;
    } else if ($highlight.hasClass("slide-math-preview")) {
      $highlight = $highlight.closest("[data-math-row]").find(".slide-math-preview").first();
    }

    runWithSyncSelectionLock(function () {
      if ($highlight && $highlight.length) {
        $highlight.addClass("sync-highlight");
        pptSyncHighlightTimer = setTimeout(function () {
          $highlight.addClass("sync-highlight");
          pptSyncHighlightTimer = null;
        }, 30);
        if (typeof $highlight[0].scrollIntoView === "function") {
          $highlight[0].scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
        }
      }
      if ($mathRow.length && $selectionTarget.hasClass("slide-hidden-math-source")) {
        $mathRow.addClass("is-editing");
        $selectionTarget = $mathRow.find(".slide-hidden-math-source").first();
      }
      if ($selectionTarget && $selectionTarget.length &&
          $selectionTarget.is("input, textarea, [contenteditable='true']")) {
        focusAndSelectElement($selectionTarget);
      }
    });
  }

  function setupCollapsedPaneResize() {
    var $panel = $(".panel-output");
    var $handle = $("#innerResizeHandle");
    var dragging = false;

    function applySplit(ratio) {
      if (!inputCollapsed || !$panel.length || !$handle.length) return;
      var panelWidth = $panel.width() || 0;
      var handleWidth = $handle.outerWidth() || 18;
      var usable = Math.max(0, panelWidth - handleWidth);
      var minPane = 260;
      var maxLeft = Math.max(minPane, usable - minPane);
      var nextLeft = Math.round(Math.max(minPane, Math.min(maxLeft, usable * ratio)));
      var nextRight = Math.max(minPane, usable - nextLeft);
      if (nextLeft + nextRight > usable) {
        nextRight = Math.max(minPane, usable - nextLeft);
      }
      $panel.css("grid-template-columns", nextLeft + "px " + handleWidth + "px " + nextRight + "px");
      if (usable > 0) {
        latexPptSplitRatio = nextLeft / usable;
        localStorage.setItem("bg_latex_ppt_split_ratio", String(latexPptSplitRatio));
      }
      refreshEditorSize();
    }

    function setRatioFromPointer(pageX) {
      if (!inputCollapsed) return;
      var rect = $panel[0].getBoundingClientRect();
      var paddingLeft = parseFloat($panel.css("padding-left")) || 0;
      var panelWidth = $panel.width() || 0;
      var handleWidth = $handle.outerWidth() || 18;
      var usable = Math.max(0, panelWidth - handleWidth);
      if (!usable) return;
      var left = pageX - rect.left - paddingLeft;
      var minPane = 260;
      left = Math.max(minPane, Math.min(usable - minPane, left));
      applySplit(left / usable);
    }

    $handle.on("mousedown", function (event) {
      if (!inputCollapsed) return;
      event.preventDefault();
      event.stopPropagation();
      dragging = true;
      $("body").addClass("resizing-columns");
    });

    $(document).on("mousemove.innerPaneResize", function (event) {
      if (!dragging) return;
      setRatioFromPointer(event.pageX);
    });

    $(document).on("mouseup.innerPaneResize", function () {
      if (!dragging) return;
      dragging = false;
      $("body").removeClass("resizing-columns");
      refreshEditorSize();
    });

    $(window).on("resize.innerPaneResize", function () {
      if (inputCollapsed) {
        applySplit(latexPptSplitRatio);
      }
    });

    return {
      applySplit: applySplit,
    };
  }

  function applyCrossSync(key, source) {
    if (!key) return;
    currentSyncKey = key;
    if (source === "latex") {
      selectPptSyncTarget(key);
    } else if (source === "ppt" && latexSyncMap[key]) {
      selectLatexSyncRange(key);
    }
  }

  function findLatexSyncKeyAtSelection() {
    if (!editor || !editor.indexFromPos) return "";
    var from = editor.indexFromPos(editor.getCursor("from"));
    var to = editor.indexFromPos(editor.getCursor("to"));
    if (from > to) {
      var tmp = from;
      from = to;
      to = tmp;
    }
    if (from === to) {
      var bestCursorKey = "";
      var bestCursorScore = Infinity;
      Object.keys(latexSyncMap).forEach(function (key) {
        var range = latexSyncMap[key];
        if (!range) return;
        var distance = 0;
        if (from < range.start) distance = range.start - from;
        else if (from > range.end) distance = from - range.end;
        else distance = Math.max(0, range.end - range.start);
        if (from >= range.start && from <= range.end) {
          distance = Math.max(0, range.end - range.start);
        }
        if (distance < bestCursorScore) {
          bestCursorScore = distance;
          bestCursorKey = key;
        }
      });
      return bestCursorKey;
    }
    var bestKey = "";
    var bestOverlap = 0;
    Object.keys(latexSyncMap).forEach(function (key) {
      var range = latexSyncMap[key];
      if (!range) return;
      var overlap = Math.max(0, Math.min(to, range.end) - Math.max(from, range.start));
      if (overlap > bestOverlap) {
        bestOverlap = overlap;
        bestKey = key;
      }
    });
    return bestKey;
  }

  function scheduleLatexSelectionSync() {
    if (syncSelectionLock || latexProgrammaticUpdate || suppressNextLatexManualSync) return;
    if (latexSelectionTimer) clearTimeout(latexSelectionTimer);
    latexSelectionTimer = setTimeout(function () {
      latexSelectionTimer = null;
      if (syncSelectionLock || latexProgrammaticUpdate || suppressNextLatexManualSync) return;
      var key = findLatexSyncKeyAtSelection();
      if (key) applyCrossSync(key, "latex");
    }, 80);
  }

  function deepClone(obj) {
    return obj == null ? obj : JSON.parse(JSON.stringify(obj));
  }

  function toCssColor(value, fallback) {
    return value || fallback || "";
  }

  function clampNumber(value, min, max, fallback) {
    var n = parseFloat(value);
    if (Number.isNaN(n)) n = fallback;
    if (Number.isNaN(n)) n = min;
    return Math.max(min, Math.min(max, n));
  }

  var SLIDE_DESIGN_WIDTH = 860;
  var SLIDE_DESIGN_HEIGHT = 484;

  function slideScale($scope) {
    return 1;
  }

  function toSlidePx(value, scale) {
    return Math.round((parseFloat(value) || 0) * (scale || 1));
  }

  function fromSlidePx(value, scale) {
    var s = scale || 1;
    return Math.round((parseFloat(value) || 0) / s);
  }

  function cssPx($el, prop, fallback) {
    var value = parseFloat($el.css(prop));
    return Number.isNaN(value) ? fallback : value;
  }

  function normalizeTable(table) {
    if (!table || !table.headers || !table.headers.length) {
      return {
        headers: ["列 1", "列 2", "列 3"],
        rows: [
          ["", "", ""],
          ["", "", ""],
        ],
      };
    }
    var headers = table.headers.slice();
    var rows = (table.rows || []).map(function (row) {
      row = row || [];
      var next = [];
      for (var i = 0; i < headers.length; i++) next.push(row[i] || "");
      return next;
    });
    if (!rows.length) rows.push(headers.map(function () { return ""; }));
    return { headers: headers, rows: rows };
  }

  function normalizePlaceholders(placeholders) {
    return (placeholders || []).map(function (ph, idx) {
      ph = ph || {};
      var figure = extractFigureReference(ph.figure || ph.label || "");
      var width = clampNumber(ph.width, 80, 760, 270);
      var height = clampNumber(ph.height, 60, 380, 190);
      return {
        type: ph.type || "image",
        label: ph.label || figure || "图片占位",
        figure: figure,
        asset: ph.asset || ph.url || ph.path || "",
        position: ph.position || "",
        x: clampNumber(ph.x, 0, SLIDE_DESIGN_WIDTH - width, 500 + idx * 12),
        y: clampNumber(ph.y, 0, SLIDE_DESIGN_HEIGHT - height, 120 + idx * 12),
        width: width,
        height: height,
      };
    });
  }

  function slideFigureRefs(slide) {
    var refs = [];
    var seen = {};

    function addFromText(text) {
      var found = collectFigureReferences(text);
      for (var i = 0; i < found.length; i++) {
        var key = normalizeFigureLabel(found[i]);
        if (!key || seen[key]) continue;
        seen[key] = true;
        refs.push(found[i]);
      }
    }

    if (!slide) return refs;
    addFromText(slide.title);
    addFromText(slide.subtitle);
    addFromText((slide.items || []).join("\n"));
    addFromText((slide.equations || []).join("\n"));
    addFromText(slide.notes || "");
    if (slide.table) {
      addFromText((slide.table.headers || []).join("\n"));
      (slide.table.rows || []).forEach(function (row) { addFromText((row || []).join("\n")); });
    }
    (slide.textboxes || []).forEach(function (tb) { addFromText(tb && tb.text); });
    (slide.placeholders || []).forEach(function (ph) { addFromText((ph && (ph.figure || ph.label)) || ""); });
    return refs;
  }

  function ensureSlideFigurePlaceholders(slide) {
    if (!slide) return;
    slide.placeholders = normalizePlaceholders(slide.placeholders);
    var existing = {};
    slide.placeholders.forEach(function (ph) {
      var key = normalizeFigureLabel(ph.figure || ph.label || "");
      if (key) {
        if (!ph.asset) {
          var figure = figurePreviewMap[key] || null;
          ph.asset = (figure && figure.url) || pickPackageImageForFigure(ph.figure || ph.label || "");
        }
        existing[key] = true;
      }
    });

    var refs = slideFigureRefs(slide);
    for (var i = 0; i < refs.length; i++) {
      var ref = refs[i];
      var key = normalizeFigureLabel(ref);
      if (!key || existing[key]) continue;
      var figure = figurePreviewMap[key] || null;
      var assetUrl = (figure && figure.url) || pickPackageImageForFigure(ref);
      if (!assetUrl) continue;
      var offset = slide.placeholders.length;
      slide.placeholders.push({
        type: "image",
        label: ref,
        figure: ref,
        asset: assetUrl,
        position: "right",
        x: 500,
        y: Math.min(260, 120 + offset * 18),
        width: 235,
        height: 165,
      });
      existing[key] = true;
    }
  }

  function ensureAllSlideFigurePlaceholders(data) {
    if (!data || !data.slides) return;
    for (var i = 0; i < data.slides.length; i++) {
      ensureSlideFigurePlaceholders(data.slides[i]);
    }
  }

  function captureHistorySnapshot() {
    if (!slidesData) return null;
    return {
      slidesData: deepClone(slidesData),
      currentSlideIdx: currentSlideIdx,
      sourceLatex: sourceLatex,
    };
  }

  function updateHistoryButtons() {
    var canUndo = !!slidesData && undoStack.length > 1;
    var canRedo = !!slidesData && redoStack.length > 0;
    $("#btnUndoPpt").prop("disabled", !canUndo);
    $("#btnRedoPpt").prop("disabled", !canRedo);
  }

  function resetHistory() {
    undoStack = [];
    redoStack = [];
    if (slidesData) {
      undoStack.push(captureHistorySnapshot());
    }
    updateHistoryButtons();
  }

  function commitHistorySnapshot(force) {
    if (!slidesData || historyLock) return;
    if (historyTimer) {
      clearTimeout(historyTimer);
      historyTimer = null;
    }
    var snap = captureHistorySnapshot();
    if (!snap) return;

    var sig = JSON.stringify(snap);
    var lastSig = undoStack.length ? JSON.stringify(undoStack[undoStack.length - 1]) : "";
    if (!force && sig === lastSig) return;

    undoStack.push(snap);
    while (undoStack.length > HISTORY_LIMIT) {
      undoStack.shift();
    }
    redoStack = [];
    updateHistoryButtons();
  }

  function scheduleHistoryCommit() {
    if (!slidesData || historyLock) return;
    if (historyTimer) clearTimeout(historyTimer);
    historyTimer = setTimeout(function () {
      historyTimer = null;
      commitHistorySnapshot(false);
    }, 250);
  }

  function restoreHistorySnapshot(snapshot, options) {
    if (!snapshot) return;
    var opts = options || {};
    var restoredSlideIdx = opts.keepCurrentSlide ? currentSlideIdx : snapshot.currentSlideIdx;
    historyLock = true;
    try {
      slidesData = deepClone(snapshot.slidesData);
      sourceLatex = snapshot.sourceLatex || sourceLatex;
      currentSlideIdx = restoredSlideIdx;

      if (!slidesData.slides) slidesData.slides = [];
      if (currentSlideIdx < 0 && slidesData.slides.length) currentSlideIdx = 0;
      if (currentSlideIdx >= slidesData.slides.length) {
        currentSlideIdx = slidesData.slides.length - 1;
      }

      fullLatex = buildLatexFromSlides(slidesData);
      updateLatexEditor(fullLatex);
      renderSlideList();
      if (currentSlideIdx >= 0 && slidesData.slides[currentSlideIdx]) {
        renderSlideEditor(slidesData.slides[currentSlideIdx]);
        selectLatexSyncForSlide(currentSlideIdx);
        $(".slide-thumb").removeClass("active").eq(currentSlideIdx).addClass("active");
      } else {
        $("#slideCanvas").html('<div class="slide-placeholder">没有可编辑的幻灯片</div>');
      }

      setActiveTab("ppt");
    } finally {
      historyLock = false;
      updateHistoryButtons();
    }
  }

  function undoPptEdit() {
    if (!slidesData || undoStack.length <= 1) return;
    var current = undoStack.pop();
    redoStack.push(current);
    if (redoStack.length > 3) redoStack.shift();
    restoreHistorySnapshot(undoStack[undoStack.length - 1], { keepCurrentSlide: true });
    setStatus("操作完成", "success");
  }

  function redoPptEdit() {
    if (!slidesData || !redoStack.length) return;
    var snap = redoStack.pop();
    undoStack.push(snap);
    if (undoStack.length > HISTORY_LIMIT) undoStack.shift();
    restoreHistorySnapshot(snap, { keepCurrentSlide: true });
    setStatus("操作完成", "success");
  }

  function latexCommentBlock(text) {
    var lines = String(text || "").split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      lines[i] = "% " + lines[i];
    }
    return lines.join("\n");
  }

  function findMatchingBrace(text, openIdx) {
    if (openIdx < 0 || text.charAt(openIdx) !== "{") return -1;
    var depth = 0;
    for (var i = openIdx; i < text.length; i++) {
      var ch = text.charAt(i);
      if (ch === "{") depth += 1;
      else if (ch === "}") {
        depth -= 1;
        if (depth === 0) return i;
      }
    }
    return -1;
  }

  function upsertLatexCommand(tex, cmd, value) {
    var pattern = "\\" + cmd;
    var idx = tex.indexOf(pattern);
    if (idx === -1) return tex + "\n" + pattern + "{" + value + "}\n";
    var openIdx = tex.indexOf("{", idx);
    if (openIdx === -1) return tex;
    var closeIdx = findMatchingBrace(tex, openIdx);
    if (closeIdx === -1) return tex;
    return tex.slice(0, openIdx + 1) + value + tex.slice(closeIdx);
  }

  function findLatexCommandValueRange(tex, cmd) {
    var pattern = "\\" + cmd;
    var idx = tex.indexOf(pattern);
    if (idx === -1) return null;
    var openIdx = tex.indexOf("{", idx);
    if (openIdx === -1) return null;
    var closeIdx = findMatchingBrace(tex, openIdx);
    if (closeIdx === -1) return null;
    return { start: openIdx + 1, end: closeIdx };
  }

  function extractRequirementHints(text) {
    return { title: "", subtitle: "", author: "", date: "" };
  }

  function chinesePageNumberToInt(text) {
    var raw = String(text || "").trim();
    if (/^\d+$/.test(raw)) return parseInt(raw, 10);
    var map = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
    return map[raw.toLowerCase()] || 0;
  }

  function inferPlaceholderPosition(text) {
    var s = String(text || "").toLowerCase();
    if (/top[- ]?right|upper[- ]?right/.test(s)) return "top-right";
    if (/top[- ]?left|upper[- ]?left/.test(s)) return "top-left";
    if (/bottom[- ]?right|lower[- ]?right/.test(s)) return "bottom-right";
    if (/bottom[- ]?left|lower[- ]?left/.test(s)) return "bottom-left";
    if (/\bleft\b/.test(s)) return "left";
    if (/\bcenter\b|middle/.test(s)) return "center";
    return "right";
  }

  function extractPlaceholderLabel(text) {
    var m = String(text || "").match(/Figure\s+\d+(?:\.\d+)?/i);
    return m ? m[0] : "image placeholder";
  }

  function extractPlaceholderTargetHint(text) {
    return "";
  }

  function extractImagePlaceholderRequirements(text) {
    var reqs = [];
    String(text || "").split(/\r?\n/).forEach(function (line) {
      if (!/(image|picture|placeholder|figure)/i.test(line)) return;
      var page = 0;
      var pageMatch = line.match(/page\s*([0-9]+)/i);
      if (pageMatch) page = parseInt(pageMatch[1], 10) || 0;
      reqs.push({ page: page, titleHint: "", position: inferPlaceholderPosition(line), label: extractPlaceholderLabel(line) });
    });
    return reqs;
  }

  function ensurePlaceholderMacroInLatex(tex) {
    if (tex.indexOf("\\kgimageplaceholder") !== -1 && tex.indexOf("\\newcommand{\\kgimageplaceholder}") !== -1) return tex;
    var beginIdx = tex.indexOf("\\begin{document}");
    var macro = "\\newcommand{\\kgimageplaceholder}[2][]{\\begin{center}\\fbox{\\parbox[c][0.28\\textheight][c]{0.34\\textwidth}{\\centering #2}}\\end{center}}\n";
    if (beginIdx === -1) return macro + tex;
    var preamble = tex.slice(0, beginIdx);
    if (preamble.indexOf("\\kgimageplaceholder") !== -1) return tex;
    return preamble + macro + tex.slice(beginIdx);
  }

  function insertPlaceholderIntoFrame(frameText, req) {
    if (frameText.indexOf("\\kgimageplaceholder") !== -1) return frameText;
    var marker = "\\kgimageplaceholder[" + (req.position || "right") + "]{" + escapeLatexText(req.label || "图片占位") + "}\n";
    var endIdx = frameText.lastIndexOf("\\end{frame}");
    if (endIdx === -1) return frameText + "\n" + marker;
    return frameText.slice(0, endIdx) + "\n" + marker + frameText.slice(endIdx);
  }

  function applyImagePlaceholderRequirements(tex, reqText) {
    var reqs = extractImagePlaceholderRequirements(reqText);
    if (!tex || !reqs.length) return tex;
    if (tex.indexOf("\\kgimageplaceholder[") !== -1) return ensurePlaceholderMacroInLatex(tex);

    var frames = [];
    var re = /\\begin\{frame\}[\s\S]*?\\end\{frame\}/g;
    var match;
    while ((match = re.exec(tex)) !== null) {
      frames.push({ start: match.index, end: re.lastIndex, text: match[0] });
    }
    if (!frames.length) return tex;

    var changed = false;
    reqs.forEach(function (req) {
      var idx = -1;
      if (req.page > 0 && req.page <= frames.length) {
        idx = req.page - 1;
      } else if (req.titleHint) {
        for (var i = 0; i < frames.length; i++) {
          if (frames[i].text.indexOf(req.titleHint) !== -1) {
            idx = i;
            break;
          }
        }
      }
      if (idx < 0) return;
      var updated = insertPlaceholderIntoFrame(frames[idx].text, req);
      if (updated !== frames[idx].text) {
        frames[idx].text = updated;
        changed = true;
      }
    });

    if (!changed) return tex;
    var out = "";
    var cursor = 0;
    frames.forEach(function (frame) {
      out += tex.slice(cursor, frame.start) + frame.text;
      cursor = frame.end;
    });
    out += tex.slice(cursor);
    return ensurePlaceholderMacroInLatex(out);
  }

  function applyCustomRequirementOverrides(tex, reqText) {
    if (!tex) return tex;
    var hints = extractRequirementHints(reqText || "");
    var beginIdx = tex.indexOf("\\begin{document}");
    if (beginIdx !== -1 && (hints.title || hints.subtitle || hints.author || hints.date)) {
      var preamble = tex.slice(0, beginIdx);
      var body = tex.slice(beginIdx);

      if (hints.title) preamble = upsertLatexCommand(preamble, "title", escapeLatexText(hints.title));
      if (hints.subtitle) preamble = upsertLatexCommand(preamble, "subtitle", escapeLatexText(hints.subtitle));
      if (hints.author) preamble = upsertLatexCommand(preamble, "author", escapeLatexText(hints.author));
      if (hints.date) preamble = upsertLatexCommand(preamble, "date", escapeLatexText(hints.date));
      tex = preamble + body;
    }

    return applyImagePlaceholderRequirements(tex, reqText || "");
  }

  function extractPreamble(tex) {
    var idx = tex.indexOf("\\begin{document}");
    if (idx === -1) return buildFallbackPreamble({});
    return tex.slice(0, idx);
  }

  function buildFallbackPreamble(meta) {
    return [
      "\\documentclass[10pt, aspectratio=169]{ctexbeamer}",
      "\\usetheme{Madrid}",
      "\\usepackage{amsmath, amssymb, amsthm}",
      "\\usepackage{graphicx}",
      "\\usepackage{booktabs}",
      "\\usepackage{multirow}",
      "\\usepackage{caption}",
      "\\usepackage{hyperref}",
      "\\usepackage{tikz}",
      "\\usetikzlibrary{shapes.callouts, tikzmark}",
      "\\usetikzlibrary{shapes, positioning}",
      "\\definecolor{myline}{RGB}{0,116,112}",
      "\\definecolor{myblue}{RGB}{40,100,180}",
      "\\setbeamertemplate{frametitle}{%",
      "  \\vspace*{0.2cm}%",
      "  \\begin{beamercolorbox}[wd=\\paperwidth, leftskip=0.5cm, rightskip=0.5cm, ht=0.3cm, dp=0pt]{whitebg}%",
      "    \\usebeamerfont{frametitle}\\textcolor{black}{\\insertframetitle}%",
      "  \\end{beamercolorbox}%",
      "  \\vspace{0pt}%",
      "  \\begin{tikzpicture}[remember picture, overlay]",
      "    \\draw[myline, line width=1.5pt]",
      "      ([yshift=-1.3cm] current page.north west) -- ([yshift=-1.3cm] current page.north east);",
      "  \\end{tikzpicture}%",
      "  \\vspace{0.1cm}%",
      "}",
      "\\setbeamertemplate{title page}{%",
      "  \\begin{tikzpicture}[remember picture, overlay]",
      "    \\draw[line width=1.5pt, color=myline]",
      "      ([yshift=-40pt] current page.north west) -- ([yshift=-40pt] current page.north east);",
      "    \\node[anchor=north west, inner sep=0, minimum width=0.25\\paperwidth,",
      "          minimum height=39pt, fill=gray!30, text=black, align=center]",
      "          at (current page.north west) {Public course in BIMSA in 2026 spring semester};",
      "  \\end{tikzpicture}%",
      "  \\vspace*{36pt}",
      "  \\begin{center}",
      "    \\begin{tikzpicture}",
      "      \\node[draw=none, inner sep=8pt, fill=white, text=black,",
      "            align=center, font=\\Huge\\bfseries] (titlebox) {\\inserttitle};",
      "      \\node[draw=none, rounded corners=2pt,",
      "            inner sep=8pt, fill=white, text=black,",
      "            align=center, font=\\large,",
      "            below=5pt of titlebox] (subtitlebox) {\\insertsubtitle};",
      "      \\node[below=5pt of subtitlebox.south east, anchor=north east, align=center, text=black] {",
      "        \\insertauthor \\\\[3pt]",
      "        \\insertdate",
      "      };",
      "    \\end{tikzpicture}",
      "  \\end{center}",
      "}",
      "\\setbeamertemplate{footline}{}",
      "\\setbeamertemplate{navigation symbols}{}",
      "\\newcommand{\\kgimageplaceholder}[2][]{\\begin{center}\\fbox{\\parbox[c][0.28\\textheight][c]{0.34\\textwidth}{\\centering #2}}\\end{center}}",
      "\\title{" + escapeLatexText(meta.title || "Presentation") + "}",
      "\\subtitle{" + escapeLatexText(meta.subtitle || "") + "}",
      "\\author{" + escapeLatexText(meta.author || "") + "}",
      "\\date{" + escapeLatexText(meta.date || "") + "}",
      ""
    ].join("\n");
  }

  function ensurePlaceholderMacro(preamble, slides) {
    var needsMacro = false;
    $.each(slides || [], function (_i, slide) {
      if (slide && slide.placeholders && slide.placeholders.length) needsMacro = true;
    });
    if (!needsMacro || preamble.indexOf("\\kgimageplaceholder") !== -1) return preamble;
    return preamble + "\n\\newcommand{\\kgimageplaceholder}[2][]{\\begin{center}\\fbox{\\parbox[c][0.28\\textheight][c]{0.34\\textwidth}{\\centering #2}}\\end{center}}\n";
  }

  function syncTitleMetaFromSlides() {
    if (!slidesData || !slidesData.slides || !slidesData.slides.length) return;
    var first = slidesData.slides[0];
    if (!first || first.type !== "title") return;
    slidesData.title = first.title != null ? first.title : (slidesData.title || "");
    slidesData.subtitle = first.subtitle != null ? first.subtitle : (slidesData.subtitle || "");
  }

  function buildTableLatex(table) {
    var headers = table.headers || [];
    var rows = table.rows || [];
    if (!headers.length) return "";

    var cols = [];
    for (var i = 0; i < headers.length; i++) cols.push("l");

    var out = [];
    out.push("  \\begin{table}[ht]");
    out.push("    \\centering");
    out.push("    \\begin{tabular}{" + cols.join("") + "}");
    out.push("      \\toprule");
    out.push("      " + headers.map(function (h) { return escapeLatexTextPreservingMath(h || ""); }).join(" & ") + " \\\\");
    out.push("      \\midrule");
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r] || [];
      out.push("      " + row.map(function (c) { return escapeLatexTextPreservingMath(c || ""); }).join(" & ") + " \\\\");
    }
    out.push("      \\bottomrule");
    out.push("    \\end{tabular}");
    out.push("  \\end{table}");
    return out.join("\n");
  }

  function buildTrackedLatexLine(prefix, rawText, suffix, key, map, slideIdx) {
    var escaped = escapeLatexTextPreservingMath(rawText || "");
    var line = prefix + escaped + (suffix || "");
    if (map && key) {
      map[key] = {
        start: prefix.length,
        end: prefix.length + escaped.length,
        slideIdx: slideIdx,
      };
    }
    return line;
  }

  function offsetLatexMap(map, offset) {
    if (!map) return {};
    Object.keys(map).forEach(function (key) {
      map[key].start += offset;
      map[key].end += offset;
    });
    return map;
  }

  function buildTableLatexTracked(table, slideIdx, map) {
    var headers = table.headers || [];
    var rows = table.rows || [];
    if (!headers.length) return "";

    var cols = [];
    for (var i = 0; i < headers.length; i++) cols.push("l");

    var out = [];
    out.push("  \\begin{table}[ht]");
    out.push("    \\centering");
    out.push("    \\begin{tabular}{" + cols.join("") + "}");
    out.push("      \\toprule");

    var headerLine = "      ";
    for (var h = 0; h < headers.length; h++) {
      var hKey = syncKey(slideIdx, "th", h);
      var hText = escapeLatexText(headers[h] || "");
      if (map) map[hKey] = { start: headerLine.length, end: headerLine.length + hText.length, slideIdx: slideIdx };
      headerLine += hText;
      if (h < headers.length - 1) headerLine += " & ";
    }
    headerLine += " \\\\";
    out.push(headerLine);
    out.push("      \\midrule");

    for (var r = 0; r < rows.length; r++) {
      var row = rows[r] || [];
      var rowLine = "      ";
      for (var c = 0; c < headers.length; c++) {
        var cKey = syncKey(slideIdx, "td", r, c);
        var cText = escapeLatexText(row[c] || "");
        if (map) map[cKey] = { start: rowLine.length, end: rowLine.length + cText.length, slideIdx: slideIdx };
        rowLine += cText;
        if (c < headers.length - 1) rowLine += " & ";
      }
      rowLine += " \\\\";
      out.push(rowLine);
    }
    out.push("      \\bottomrule");
    out.push("    \\end{tabular}");
    out.push("  \\end{table}");

    var text = "";
    var cursor = 0;
    for (var j = 0; j < out.length; j++) {
      var lineMap = {};
      if (j === 4) {
        for (var hh = 0; hh < headers.length; hh++) {
          var hk = syncKey(slideIdx, "th", hh);
          if (map && map[hk]) lineMap[hk] = map[hk];
        }
      } else if (j > 5 && j < 6 + rows.length) {
        var rr = j - 6;
        for (var cc = 0; cc < headers.length; cc++) {
          var ck = syncKey(slideIdx, "td", rr, cc);
          if (map && map[ck]) lineMap[ck] = map[ck];
        }
      }
      offsetLatexMap(lineMap, cursor);
      text += out[j];
      cursor += out[j].length;
      if (j < out.length - 1) {
        text += "\n";
        cursor += 1;
      }
    }
    return text;
  }

  function placeholderPositionForLatex(ph) {
    if (ph.position) return ph.position;
    var x = parseFloat(ph.x) || 0;
    var y = parseFloat(ph.y) || 0;
    if (x > 500 && y < 220) return "top-right";
    if (x < 280 && y < 220) return "top-left";
    if (x > 500 && y >= 220) return "bottom-right";
    if (x < 280 && y >= 220) return "bottom-left";
    return "center";
  }

  function buildPlaceholderLatex(ph) {
    ph = ph || {};
    var options = [];
    var figureRef = extractFigureReference(ph.figure || ph.label || "");
    if (figureRef) options.push("figure=" + figureRef);
    var position = placeholderPositionForLatex(ph);
    if (position) options.push(position);
    options.push("x=" + Math.round(clampNumber(ph.x, 0, SLIDE_DESIGN_WIDTH, 500)));
    options.push("y=" + Math.round(clampNumber(ph.y, 0, SLIDE_DESIGN_HEIGHT, 120)));
    options.push("width=" + Math.round(clampNumber(ph.width, 80, SLIDE_DESIGN_WIDTH, 235)));
    options.push("height=" + Math.round(clampNumber(ph.height, 60, SLIDE_DESIGN_HEIGHT, 165)));
    var optText = options.join(",");
    return "  \\kgimageplaceholder[" + escapeLatexText(optText) + "]{" +
      escapeLatexText(ph.label || figureRef || "图片占位") + "}";
  }

  function buildImageLatex(img) {
    img = img || {};
    var imgPath = String(img.path || "").replace(/^\/+/, "");
    if (!imgPath) return "";
    var width = Math.round(clampNumber(img.width, 60, SLIDE_DESIGN_WIDTH, 220));
    var height = Math.round(clampNumber(img.height, 45, SLIDE_DESIGN_HEIGHT, 150));
    var x = Math.round(clampNumber(img.x, 0, SLIDE_DESIGN_WIDTH, 40));
    var y = Math.round(clampNumber(img.y, 0, SLIDE_DESIGN_HEIGHT, 170));
    return "    \\includegraphics[width=" + width + "px,height=" + height +
      "px,keepaspectratio,x=" + x + ",y=" + y + "]{" + imgPath + "}";
  }

  function slidePxToCm(value, totalPx, totalCm) {
    return (Number(value) || 0) / totalPx * totalCm;
  }

  function buildCalloutLatex(callout) {
    callout = callout || {};
    var text = repairPptLatexArtifacts(callout.text || "");
    if (!text.trim()) return "";
    var width = clampNumber(callout.width, 120, SLIDE_DESIGN_WIDTH, 250);
    var height = clampNumber(callout.height, 50, SLIDE_DESIGN_HEIGHT, 90);
    var x = clampNumber(callout.x, 0, SLIDE_DESIGN_WIDTH - width, 130);
    var y = clampNumber(callout.y, 0, SLIDE_DESIGN_HEIGHT - height, 180);
    var centerX = slidePxToCm(x + width / 2, SLIDE_DESIGN_WIDTH, 16);
    var centerY = slidePxToCm(y + height / 2, SLIDE_DESIGN_HEIGHT, 9);
    var textWidth = Math.max(2.2, slidePxToCm(width - 24, SLIDE_DESIGN_WIDTH, 16));
    var fontSize = clampNumber(callout.fontSize, 8, 28, 12);
    var align = /^(left|right|center)$/.test(callout.align || "") ? callout.align : "center";
    return [
      "  \\begin{tikzpicture}[remember picture, overlay]",
      "    \\node[rectangle callout, callout relative pointer={(-0.45cm,-0.35cm)}, draw=blue, fill=white, rounded corners, text width=" + textWidth.toFixed(2) + "cm, align=" + align + ", font=\\fontsize{" + fontSize + "}{" + Math.round(fontSize * 1.2) + "}\\selectfont] at ([xshift=" + centerX.toFixed(2) + "cm,yshift=-" + centerY.toFixed(2) + "cm] current page.north west)",
      "      {" + escapeLatexTextPreservingMath(text) + "};",
      "  \\end{tikzpicture}"
    ].join("\n");
  }

  function cleanEquationForPpt(eq) {
    var s = String(eq || "").trim();
    if (!s) return "";
    s = s.replace(/^\[\s*/, "");
    s = s.replace(/\\\[/g, "");
    var stopPatterns = [
      /\\\]/,
      /\\item(?:<[^>]*>)?\b/,
      /\\begin\{(?:itemize|enumerate|description|tikzpicture)\}/,
      /\\end\{(?:itemize|enumerate|description|frame|tikzpicture)\}/,
      /\\onslide/,
      /\\only/,
      /\\uncover/,
      /\\node\b/,
      /\\tikz/
    ];
    for (var i = 0; i < stopPatterns.length; i++) {
      var match = s.match(stopPatterns[i]);
      if (match && match.index !== undefined) {
        s = s.slice(0, match.index);
      }
    }
    return s.replace(/\s+/g, " ").trim();
  }

  function equationSignature(eq) {
    return cleanEquationForPpt(eq).replace(/\s+/g, "");
  }

  function normalizeSlideEquations(slide) {
    if (!slide || !slide.equations) return;
    var seen = {};
    var cleaned = [];
    $.each(slide.equations, function (_idx, eq) {
      var next = cleanEquationForPpt(eq);
      var sig = equationSignature(next);
      if (!next || !sig || seen[sig]) return;
      seen[sig] = true;
      cleaned.push(next);
    });
    slide.equations = cleaned;
  }

  function mergeEditedImagePositions(nextData, previousData) {
    if (!nextData || !nextData.slides || !previousData || !previousData.slides) return;
    for (var i = 0; i < nextData.slides.length; i++) {
      var nextSlide = nextData.slides[i] || {};
      var prevSlide = previousData.slides[i] || {};
      var prevPlaceholders = {};
      normalizePlaceholders(prevSlide.placeholders || []).forEach(function (ph) {
        var key = normalizeFigureLabel(ph.figure || ph.label || "");
        if (key) prevPlaceholders[key] = ph;
      });
      nextSlide.placeholders = normalizePlaceholders(nextSlide.placeholders || []).map(function (ph, phIdx) {
        var key = normalizeFigureLabel(ph.figure || ph.label || "");
        var prev = key ? prevPlaceholders[key] : null;
        if (prev) {
          ph.x = prev.x;
          ph.y = prev.y;
          ph.width = prev.width;
          ph.height = prev.height;
          ph.asset = ph.asset || prev.asset || "";
        }
        var savedPh = editedImageGeometry.placeholders[placeholderGeometryKey(i, phIdx, ph)];
        if (savedPh) {
          ph.x = savedPh.x;
          ph.y = savedPh.y;
          ph.width = savedPh.width;
          ph.height = savedPh.height;
        }
        return ph;
      });

      if ((!nextSlide.images || !nextSlide.images.length) && prevSlide.images && prevSlide.images.length) {
        nextSlide.images = deepClone(prevSlide.images);
      } else if (nextSlide.images && nextSlide.images.length && prevSlide.images && prevSlide.images.length) {
        var prevImagesByPath = {};
        prevSlide.images.forEach(function (img) {
          var key = String((img && img.path) || "");
          if (key) prevImagesByPath[key] = img;
        });
        nextSlide.images.forEach(function (img) {
          var key = String((img && img.path) || "");
          var prev = key ? prevImagesByPath[key] : null;
          if (prev) {
            img.x = prev.x;
            img.y = prev.y;
            img.width = prev.width;
            img.height = prev.height;
          }
        });
      }
      applyEditedGeometryToSlide(nextSlide, i);
    }
  }

  function buildTitleSlideLatex() {
    return [
      "{",
      "\\setbeamertemplate{footline}{}",
      "\\begin{frame}",
      "  \\titlepage",
      "\\end{frame}",
      "}"
    ].join("\n");
  }

  function buildTocSlideLatex(slide) {
    var items = slide.items || [];
    var out = [];
    out.push("\\begin{frame}{" + escapeLatexTextPreservingMath(slide.title || "Contents") + "}");
    out.push("  \\vfill");
    out.push("  \\begin{center}");
    out.push("    \\begin{minipage}{0.7\\textwidth}");
    out.push("      \\begin{itemize}");
    out.push("        \\setlength{\\itemsep}{0.3\\baselineskip}");
    for (var i = 0; i < items.length; i++) {
      out.push(
        "        \\item[\\textcolor{black}{\\textbf{" + (i + 1) + ".}}] " +
        "\\textcolor{black}{" + escapeLatexTextPreservingMath(items[i] || "") + "}"
      );
    }
    out.push("      \\end{itemize}");
    out.push("    \\end{minipage}");
    out.push("  \\end{center}");
    out.push("  \\vfill");
    out.push("\\end{frame}");
    return out.join("\n");
  }

  function buildTocSlideLatexTracked(slide, slideIdx, map) {
    var items = slide.items || [];
    var out = [];
    var localMap = {};

    function addLine(line, lineMap) {
      var lineIdx = out.length;
      out.push(line);
      if (lineMap) {
        Object.keys(lineMap).forEach(function (key) {
          localMap[key] = {
            start: lineMap[key].start,
            end: lineMap[key].end,
            slideIdx: slideIdx,
            line: lineIdx,
          };
        });
      }
    }

    function addTrackedLine(prefix, rawText, suffix, key) {
      var lineMap = {};
      var line = buildTrackedLatexLine(prefix, rawText, suffix, key, lineMap, slideIdx);
      addLine(line, lineMap);
    }

    addTrackedLine("\\begin{frame}{", slide.title || "Contents", "}", syncKey(slideIdx, "title"));
    addLine("  \\vfill");
    addLine("  \\begin{center}");
    addLine("    \\begin{minipage}{0.7\\textwidth}");
    addLine("      \\begin{itemize}");
    addLine("        \\setlength{\\itemsep}{0.3\\baselineskip}");
    for (var i = 0; i < items.length; i++) {
      var prefix = "        \\item[\\textcolor{black}{\\textbf{" + (i + 1) + ".}}] \\textcolor{black}{";
      addTrackedLine(prefix, items[i] || "", "}", syncKey(slideIdx, "item", i));
    }
    addLine("      \\end{itemize}");
    addLine("    \\end{minipage}");
    addLine("  \\end{center}");
    addLine("  \\vfill");
    addLine("\\end{frame}");

    var text = out.join("\n");
    var cursor = 0;
    for (var k = 0; k < out.length; k++) {
      Object.keys(localMap).forEach(function (key) {
        var range = localMap[key];
        if (range.line === k) {
          map[key] = { start: range.start + cursor, end: range.end + cursor, slideIdx: slideIdx };
        }
      });
      cursor += out[k].length + (k < out.length - 1 ? 1 : 0);
    }
    return text;
  }

  function buildContentSlideLatex(slide) {
    var out = [];
    out.push("\\begin{frame}{" + richHtmlToLatex(slide.titleRichHtml || "", slide.title || "") + "}");

    if (slide.subtitle) {
      out.push("  \\textit{" + richHtmlToLatex(slide.subtitleRichHtml || "", slide.subtitle) + "}");
      out.push("  \\vspace{0.3cm}");
    }

    if (slide.table && slide.table.headers && slide.table.headers.length) {
      out.push(buildTableLatex(slide.table));
    }

    if (slide.placeholders && slide.placeholders.length) {
      for (var p = 0; p < slide.placeholders.length; p++) {
        out.push(buildPlaceholderLatex(slide.placeholders[p]));
      }
    }

    if (slide.items && slide.items.length) {
      out.push("  \\begin{itemize}");
      for (var i = 0; i < slide.items.length; i++) {
        out.push("    \\item " + richHtmlToLatex((slide.itemRichHtml || [])[i] || "", slide.items[i] || ""));
      }
      out.push("  \\end{itemize}");
    }

    if (slide.equations && slide.equations.length) {
      for (var j = 0; j < slide.equations.length; j++) {
        out.push("  \\[");
        out.push("    " + (slide.equations[j] || ""));
        out.push("  \\]");
      }
    }

    if (slide.textboxes && slide.textboxes.length) {
      for (var k = 0; k < slide.textboxes.length; k++) {
        var tb = slide.textboxes[k] || {};
        if (!tb.text) continue;
        var boxText = richHtmlToLatex(tb.richHtml || "", tb.text);
        if (tb.fontSize) {
          boxText = "{\\fontsize{" + tb.fontSize + "}{" + Math.round(tb.fontSize * 1.2) + "}\\selectfont " + boxText + "}";
        }
        out.push("  \\begin{center}");
        out.push("    \\fbox{\\parbox{0.92\\linewidth}{" + boxText + "}}");
        out.push("  \\end{center}");
      }
    }

    if (slide.images && slide.images.length) {
      for (var m = 0; m < slide.images.length; m++) {
        var img = slide.images[m] || {};
        var imgLatex = buildImageLatex(img);
        if (!imgLatex) continue;
        out.push("  \\begin{center}");
        out.push(imgLatex);
        out.push("  \\end{center}");
      }
    }

    if (slide.callouts && slide.callouts.length) {
      for (var c = 0; c < slide.callouts.length; c++) {
        var calloutLatex = buildCalloutLatex(slide.callouts[c]);
        if (calloutLatex) out.push(calloutLatex);
      }
    }

    if (slide.notes) {
      out.push(latexCommentBlock(slide.notes));
    }

    out.push("\\end{frame}");
    return out.join("\n");
  }

  function buildContentSlideLatexTracked(slide, slideIdx, map) {
    var out = [];
    var localMap = {};

    function addLine(line, lineMap) {
      var lineIdx = out.length;
      out.push(line);
      if (lineMap) {
        Object.keys(lineMap).forEach(function (key) {
          localMap[key] = {
            start: lineMap[key].start,
            end: lineMap[key].end,
            slideIdx: slideIdx,
            line: lineIdx,
          };
        });
      }
    }

    function addTrackedLine(prefix, rawText, suffix, key) {
      var lineMap = {};
      var line = buildTrackedLatexLine(prefix, rawText, suffix, key, lineMap, slideIdx);
      addLine(line, lineMap);
    }

    if (slide.titleRichHtml) {
      addLine("\\begin{frame}{" + richHtmlToLatex(slide.titleRichHtml, slide.title || "") + "}");
    } else {
      addTrackedLine("\\begin{frame}{", slide.title || "", "}", syncKey(slideIdx, "title"));
    }

    if (slide.subtitle) {
      if (slide.subtitleRichHtml) {
        addLine("  \\textit{" + richHtmlToLatex(slide.subtitleRichHtml, slide.subtitle) + "}");
      } else {
        addTrackedLine("  \\textit{", slide.subtitle, "}", syncKey(slideIdx, "subtitle"));
      }
      addLine("  \\vspace{0.3cm}");
    }

    if (slide.table && slide.table.headers && slide.table.headers.length) {
      var tableMap = {};
      var tableText = buildTableLatexTracked(slide.table, slideIdx, tableMap);
      var tableStartLine = out.join("\n").length + (out.length ? 1 : 0);
      addLine(tableText);
      Object.keys(tableMap).forEach(function (key) {
        localMap[key] = {
          start: tableMap[key].start + tableStartLine,
          end: tableMap[key].end + tableStartLine,
          slideIdx: slideIdx,
          absolute: true,
        };
      });
    }

    if (slide.placeholders && slide.placeholders.length) {
      for (var p = 0; p < slide.placeholders.length; p++) {
        var ph = slide.placeholders[p] || {};
        var phOptions = [];
        var phFigureRef = extractFigureReference(ph.figure || ph.label || "");
        if (phFigureRef) phOptions.push("figure=" + phFigureRef);
        phOptions.push(placeholderPositionForLatex(ph));
        phOptions.push("x=" + Math.round(clampNumber(ph.x, 0, SLIDE_DESIGN_WIDTH, 500)));
        phOptions.push("y=" + Math.round(clampNumber(ph.y, 0, SLIDE_DESIGN_HEIGHT, 120)));
        phOptions.push("width=" + Math.round(clampNumber(ph.width, 80, SLIDE_DESIGN_WIDTH, 235)));
        phOptions.push("height=" + Math.round(clampNumber(ph.height, 60, SLIDE_DESIGN_HEIGHT, 165)));
        var phPrefix = "  \\kgimageplaceholder[" + escapeLatexText(phOptions.join(",")) + "]{";
        addTrackedLine(phPrefix, ph.label || "图片占位", "}", syncKey(slideIdx, "placeholder", p));
      }
    }

    if (slide.items && slide.items.length) {
      addLine("  \\begin{itemize}");
      for (var i = 0; i < slide.items.length; i++) {
        var itemRich = (slide.itemRichHtml || [])[i] || "";
        if (itemRich) {
          addLine("    \\item " + richHtmlToLatex(itemRich, slide.items[i] || ""));
        } else {
          addTrackedLine("    \\item ", slide.items[i] || "", "", syncKey(slideIdx, "item", i));
        }
      }
      addLine("  \\end{itemize}");
    }

    if (slide.equations && slide.equations.length) {
      for (var j = 0; j < slide.equations.length; j++) {
        addLine("  \\[");
        var eq = slide.equations[j] || "";
        var eqLine = "    " + eq;
        var eqKey = syncKey(slideIdx, "equation", j);
        addLine(eqLine, (function () {
          var m = {};
          m[eqKey] = { start: 4, end: 4 + eq.length, slideIdx: slideIdx };
          return m;
        })());
        addLine("  \\]");
      }
    }

    if (slide.textboxes && slide.textboxes.length) {
      for (var k = 0; k < slide.textboxes.length; k++) {
        var tb = slide.textboxes[k] || {};
        if (!tb.text) continue;
        var tbPrefix = "    \\fbox{\\parbox{0.92\\linewidth}{";
        var tbSuffix = "}}";
        if (tb.fontSize) {
          tbPrefix += "{\\fontsize{" + tb.fontSize + "}{" + Math.round(tb.fontSize * 1.2) + "}\\selectfont ";
          tbSuffix += "}";
        }
        addLine("  \\begin{center}");
        if (tb.richHtml) {
          addLine(tbPrefix + richHtmlToLatex(tb.richHtml, tb.text) + tbSuffix);
        } else {
          addTrackedLine(tbPrefix, tb.text, tbSuffix, syncKey(slideIdx, "textbox", k));
        }
        addLine("  \\end{center}");
      }
    }

    if (slide.images && slide.images.length) {
      for (var m = 0; m < slide.images.length; m++) {
        var img = slide.images[m] || {};
        var imgLatex = buildImageLatex(img);
        if (!imgLatex) continue;
        addLine("  \\begin{center}");
        addLine(imgLatex);
        addLine("  \\end{center}");
      }
    }

    if (slide.callouts && slide.callouts.length) {
      for (var c = 0; c < slide.callouts.length; c++) {
        var callout = slide.callouts[c] || {};
        var text = repairPptLatexArtifacts(callout.text || "");
        if (!text.trim()) continue;
        var width = clampNumber(callout.width, 120, SLIDE_DESIGN_WIDTH, 250);
        var height = clampNumber(callout.height, 50, SLIDE_DESIGN_HEIGHT, 90);
        var x = clampNumber(callout.x, 0, SLIDE_DESIGN_WIDTH - width, 130);
        var y = clampNumber(callout.y, 0, SLIDE_DESIGN_HEIGHT - height, 180);
        var centerX = slidePxToCm(x + width / 2, SLIDE_DESIGN_WIDTH, 16);
        var centerY = slidePxToCm(y + height / 2, SLIDE_DESIGN_HEIGHT, 9);
        var textWidth = Math.max(2.2, slidePxToCm(width - 24, SLIDE_DESIGN_WIDTH, 16));
        var fontSize = clampNumber(callout.fontSize, 8, 28, 12);
        var align = /^(left|right|center)$/.test(callout.align || "") ? callout.align : "center";
        addLine("  \\begin{tikzpicture}[remember picture, overlay]");
        addLine("    \\node[rectangle callout, callout relative pointer={(-0.45cm,-0.35cm)}, draw=blue, fill=white, rounded corners, text width=" + textWidth.toFixed(2) + "cm, align=" + align + ", font=\\fontsize{" + fontSize + "}{" + Math.round(fontSize * 1.2) + "}\\selectfont] at ([xshift=" + centerX.toFixed(2) + "cm,yshift=-" + centerY.toFixed(2) + "cm] current page.north west)");
        addTrackedLine("      {", text, "};", syncKey(slideIdx, "callout", c));
        addLine("  \\end{tikzpicture}");
      }
    }

    if (slide.notes) {
      var noteLines = String(slide.notes || "").split(/\r?\n/);
      for (var n = 0; n < noteLines.length; n++) {
        addTrackedLine("% ", noteLines[n], "", syncKey(slideIdx, "notes"));
      }
    }

    addLine("\\end{frame}");

    var text = out.join("\n");
    var cursor = 0;
    for (var lineIdx = 0; lineIdx < out.length; lineIdx++) {
      Object.keys(localMap).forEach(function (key) {
        var range = localMap[key];
        if (range.absolute) {
          map[key] = { start: range.start, end: range.end, slideIdx: slideIdx };
        } else if (range.line === lineIdx) {
          map[key] = { start: range.start + cursor, end: range.end + cursor, slideIdx: slideIdx };
        }
      });
      cursor += out[lineIdx].length + (lineIdx < out.length - 1 ? 1 : 0);
    }
    return text;
  }

  function wrapReviewBackgroundLatex(slideText) {
    var prefix = REVIEW_BACKGROUND_LATEX_PREFIX + "\n";
    return {
      text: prefix + slideText + "\n\n}",
      offset: prefix.length,
    };
  }

  function ensureReviewBackgroundPreamble(preamble, slides) {
    var needsReviewBackground = (slides || []).some(function (slide) {
      return slide && slide.reviewBackground;
    });
    if (!needsReviewBackground) return preamble;
    if (!/\\usepackage(?:\[[^\]]*\])?\{tikz\}/.test(preamble)) {
      preamble = preamble.replace(/(\\usetheme\{[^}]+\}\s*)/, "$1\n\\usepackage{tikz}\n");
    }
    if (preamble.indexOf("\\usetikzlibrary{shapes, positioning}") === -1) {
      preamble = preamble.replace(/(\\usepackage(?:\[[^\]]*\])?\{tikz\}\s*)/, "$1\\usetikzlibrary{shapes, positioning}\n");
    }
    return preamble;
  }

  function buildLatexFromSlides(data) {
    var trackedMap = {};
    var source = sourceLatex || fullLatex || "";
    var preamble = extractPreamble(source);
    preamble = upsertLatexCommand(preamble, "title", escapeLatexText(data.title || "Presentation"));
    preamble = upsertLatexCommand(preamble, "subtitle", escapeLatexText(data.subtitle || ""));
    preamble = upsertLatexCommand(preamble, "author", escapeLatexText(data.author || ""));
    preamble = upsertLatexCommand(preamble, "date", escapeLatexText(data.date || ""));
    preamble = ensurePlaceholderMacro(preamble, data.slides || []);
    preamble = ensureReviewBackgroundPreamble(preamble, data.slides || []);

    var preambleTitleRange = findLatexCommandValueRange(preamble, "title");
    if (preambleTitleRange) {
      trackedMap[syncKey(0, "title")] = {
        start: preambleTitleRange.start,
        end: preambleTitleRange.end,
        slideIdx: 0,
      };
    }
    var preambleSubtitleRange = findLatexCommandValueRange(preamble, "subtitle");
    if (preambleSubtitleRange) {
      trackedMap[syncKey(0, "subtitle")] = {
        start: preambleSubtitleRange.start,
        end: preambleSubtitleRange.end,
        slideIdx: 0,
      };
    }

    var body = [];
    var slides = data.slides || [];
    for (var i = 0; i < slides.length; i++) {
      var slide = slides[i] || {};
      var slideMap = {};
      var slideText = "";
      if (slide.type === "title") slideText = buildTitleSlideLatex();
      else if (slide.type === "toc") slideText = buildTocSlideLatexTracked(slide, i, slideMap);
      else slideText = buildContentSlideLatexTracked(slide, i, slideMap);
      if (slide.reviewBackground) {
        var wrappedSlide = wrapReviewBackgroundLatex(slideText);
        slideText = wrappedSlide.text;
        Object.keys(slideMap).forEach(function (key) {
          slideMap[key].start += wrappedSlide.offset;
          slideMap[key].end += wrappedSlide.offset;
        });
      }
      slideMap[syncKey(i, "frame")] = {
        start: 0,
        end: slideText.length,
        slideIdx: i,
        line: 0,
        absolute: true,
      };
      var bodyPrefixLength = body.length ? body.join("\n\n").length + 2 : 0;
      Object.keys(slideMap).forEach(function (key) {
        trackedMap[key] = {
          start: slideMap[key].start + bodyPrefixLength,
          end: slideMap[key].end + bodyPrefixLength,
          slideIdx: slideMap[key].slideIdx,
        };
      });
      body.push(slideText);
    }

    var prefix = preamble + "\n\\begin{document}\n\n";
    Object.keys(trackedMap).forEach(function (key) {
      trackedMap[key].start += prefix.length;
      trackedMap[key].end += prefix.length;
    });
    if (preambleTitleRange) {
      trackedMap[syncKey(0, "title")] = {
        start: preambleTitleRange.start,
        end: preambleTitleRange.end,
        slideIdx: 0,
      };
    }
    if (preambleSubtitleRange) {
      trackedMap[syncKey(0, "subtitle")] = {
        start: preambleSubtitleRange.start,
        end: preambleSubtitleRange.end,
        slideIdx: 0,
      };
    }
    latexSyncMap = trackedMap;
    return prefix + body.join("\n\n") + "\n\n\\end{document}\n";
  }

  function updateLatexEditor(tex) {
    var scrollInfo = editor.getScrollInfo();
    clearLatexSyncMarks();
    if (latexManualSyncTimer) {
      clearTimeout(latexManualSyncTimer);
      latexManualSyncTimer = null;
    }
    if (latexSelectionTimer) {
      clearTimeout(latexSelectionTimer);
      latexSelectionTimer = null;
    }
    suppressNextLatexManualSync = true;
    latexProgrammaticUpdate = true;
    editor.setValue(tex || "");
    latexProgrammaticUpdate = false;
    setTimeout(function () {
      suppressNextLatexManualSync = false;
    }, 120);
    editor.scrollTo(scrollInfo.left, scrollInfo.top);
  }

  function rebuildLatexSyncMapFromSource(data, tex) {
    var map = {};
    var source = String(tex || "");
    if (!data || !data.slides || !source) {
      latexSyncMap = map;
      return;
    }

    var frames = [];
    var frameRe = /\\begin\{frame\}[\s\S]*?\\end\{frame\}/g;
    var match;
    while ((match = frameRe.exec(source)) !== null) {
      frames.push({ start: match.index, end: frameRe.lastIndex, text: match[0] });
    }

    function addRange(key, start, end, slideIdx) {
      if (!key || start < 0 || end <= start) return;
      map[key] = { start: start, end: end, slideIdx: slideIdx };
    }

    function addBraceValue(frame, commandStart, key, slideIdx) {
      var open = source.indexOf("{", commandStart);
      if (open === -1 || open >= frame.end) return;
      var close = findMatchingBrace(source, open);
      if (close === -1 || close > frame.end) return;
      addRange(key, open + 1, close, slideIdx);
    }

    for (var i = 0; i < data.slides.length && i < frames.length; i++) {
      var slide = data.slides[i] || {};
      var frame = frames[i];
      addRange(syncKey(i, "frame"), frame.start, frame.end, i);

      var headerIdx = source.indexOf("\\begin{frame}", frame.start);
      var afterHeader = headerIdx + "\\begin{frame}".length;
      if (source.charAt(afterHeader) === "{") {
        var titleClose = findMatchingBrace(source, afterHeader);
        if (titleClose !== -1 && titleClose <= frame.end) {
          addRange(syncKey(i, "title"), afterHeader + 1, titleClose, i);
        }
      }
      var ftIdx = source.indexOf("\\frametitle", frame.start);
      if (ftIdx !== -1 && ftIdx < frame.end) addBraceValue(frame, ftIdx, syncKey(i, "title"), i);

      var local = frame.text;
      var itemMatches = [];
      var itemRe = /\\item(?:<[^>]*>)?(?:\[[\s\S]*?\])?\s*/g;
      var itemMatch;
      while ((itemMatch = itemRe.exec(local)) !== null) {
        itemMatches.push({ start: frame.start + itemMatch.index, contentStart: frame.start + itemRe.lastIndex });
      }
      for (var itemIdx = 0; itemIdx < itemMatches.length; itemIdx++) {
        var itemEnd = itemIdx + 1 < itemMatches.length ? itemMatches[itemIdx + 1].start : frame.end;
        var envEnd = source.indexOf("\\end{itemize}", itemMatches[itemIdx].contentStart);
        if (envEnd !== -1 && envEnd < itemEnd) itemEnd = envEnd;
        addRange(syncKey(i, "item", itemIdx), itemMatches[itemIdx].contentStart, itemEnd, i);
      }

      var eqIdx = 0;
      var eqRe = /\\\[([\s\S]*?)\\\]/g;
      var eqMatch;
      while ((eqMatch = eqRe.exec(local)) !== null) {
        addRange(syncKey(i, "equation", eqIdx), frame.start + eqMatch.index + 2, frame.start + eqRe.lastIndex - 2, i);
        eqIdx += 1;
      }

      var phIdx = 0;
      var phRe = /\\(?:kgimageplaceholder|imageplaceholder|pptimageplaceholder)\s*(?:\[[^\]]*\])?\s*\{/g;
      var phMatch;
      while ((phMatch = phRe.exec(local)) !== null) {
        var phOpen = frame.start + phRe.lastIndex - 1;
        var phClose = findMatchingBrace(source, phOpen);
        if (phClose !== -1 && phClose <= frame.end) {
          addRange(syncKey(i, "placeholder", phIdx), phOpen + 1, phClose, i);
          phIdx += 1;
        }
      }

      if (slide.notes) {
        var noteIdx = source.indexOf("%", frame.start);
        if (noteIdx !== -1 && noteIdx < frame.end) addRange(syncKey(i, "notes"), noteIdx, frame.end, i);
      }
    }

    latexSyncMap = map;
  }

  function parseLatexIntoPptFromEditor() {
    var tex = editor.getValue ? editor.getValue() : fullLatex;
    fullLatex = tex || "";
    sourceLatex = fullLatex;
    $("#btnCopy, #btnDownloadTex, #btnConvertPpt").prop("disabled", !fullLatex);
    updateDownloadPptxButton();
    if (!fullLatex.trim()) return;

    var seq = ++latexManualSyncSeq;
    $.ajax({
      url: "/beamer-generator/api/parse-slides",
      method: "POST",
      contentType: "application/json",
      data: JSON.stringify({ latex: fullLatex }),
      success: function (data) {
        if (seq !== latexManualSyncSeq || !data || data.error || !data.slides) return;
        var previousSlidesData = slidesData ? deepClone(slidesData) : null;
        for (var i = 0; i < data.slides.length; i++) {
          if (!data.slides[i].images) data.slides[i].images = [];
          if (!data.slides[i].textboxes) data.slides[i].textboxes = [];
          if (!data.slides[i].callouts) data.slides[i].callouts = [];
          normalizeSlideEditableText(data.slides[i]);
          data.slides[i].placeholders = normalizePlaceholders(data.slides[i].placeholders);
          if (data.slides[i].table) data.slides[i].table = normalizeTable(data.slides[i].table);
        }
        mergeEditedImagePositions(data, previousSlidesData);
        ensureAllSlideFigurePlaceholders(data);
        var previousSlideIdx = currentSlideIdx;
        slidesData = data;
        if (currentSlideIdx < 0 && data.slides.length) currentSlideIdx = 0;
        if (currentSlideIdx >= data.slides.length) currentSlideIdx = data.slides.length - 1;
        rebuildLatexSyncMapFromSource(slidesData, fullLatex);
        renderSlideList();
        if (currentSlideIdx >= 0 && slidesData.slides[currentSlideIdx]) {
          renderSlideEditor(slidesData.slides[currentSlideIdx]);
          $(".slide-thumb").removeClass("active").eq(currentSlideIdx).addClass("active");
          if (previousSlideIdx >= 0 && previousSlideIdx < slidesData.slides.length) {
            currentSlideIdx = previousSlideIdx;
            $(".slide-thumb").removeClass("active").eq(currentSlideIdx).addClass("active");
            renderSlideEditor(slidesData.slides[currentSlideIdx]);
          }
        }
        $("#tabPpt").prop("disabled", false);
        updateHistoryButtons();
      }
    });
  }

  function scheduleLatexManualSync() {
    if (latexProgrammaticUpdate || suppressNextLatexManualSync || syncSelectionLock) return;
    if (latexManualSyncTimer) clearTimeout(latexManualSyncTimer);
    latexManualSyncTimer = setTimeout(function () {
      latexManualSyncTimer = null;
      if (latexProgrammaticUpdate || suppressNextLatexManualSync || syncSelectionLock) return;
      parseLatexIntoPptFromEditor();
    }, 650);
  }

  function syncLatexFromSlides() {
    if (!slidesData) return;
    latexManualSyncSeq += 1;
    var keepSlideIdx = currentSlideIdx;
    syncTitleMetaFromSlides();
    ensureAllSlideFigurePlaceholders(slidesData);
    fullLatex = buildLatexFromSlides(slidesData);
    fullLatex = applyCustomRequirementOverrides(fullLatex, currentCustomRequirements);
    sourceLatex = fullLatex;
    updateLatexEditor(fullLatex);
    rebuildLatexSyncMapFromSource(slidesData, fullLatex);
    currentSlideIdx = keepSlideIdx;
    renderSlideList();
    if (currentSlideIdx >= 0) {
      $(".slide-thumb").removeClass("active").eq(currentSlideIdx).addClass("active");
    }
  }

  function syncCurrentSlideToLatex() {
    if (!slidesData || currentSlideIdx < 0 || !slidesData.slides[currentSlideIdx]) return;
    syncLatexFromSlides();
    if (currentSlideIdx >= 0) {
      $(".slide-thumb").removeClass("active").eq(currentSlideIdx).addClass("active");
    }
  }

  function scheduleLatexSync() {
    if (!slidesData) return;
    if (latexSyncTimer) clearTimeout(latexSyncTimer);
    latexSyncTimer = setTimeout(function () {
      latexSyncTimer = null;
      syncCurrentSlideToLatex();
    }, 120);
  }

  function applyInputCollapsedState() {
    $(".container").toggleClass("input-collapsed", inputCollapsed);
    $(".panel-input").prop("hidden", inputCollapsed);
    $("#btnToggleInputPanel")
      .text(inputCollapsed ? ">>" : "<<")
      .attr("aria-label", inputCollapsed ? "Expand left panel" : "Collapse left panel")
      .attr("title", inputCollapsed ? "Expand left panel" : "Collapse left panel");
    $("#innerResizeHandle").toggle(inputCollapsed);

    if (inputCollapsed) {
      $("#viewLatex, #viewPpt").addClass("active").show();
      $(".latex-actions, .ppt-actions").show();
      if (collapsedPaneResize) {
        collapsedPaneResize.applySplit(latexPptSplitRatio);
      }
    } else {
      $(".panel-output").css("grid-template-columns", "");
      setActiveTab(activeTab || "latex");
    }

    refreshEditorSize();
  }

  function setActiveTab(tab) {
    if (tab !== "latex" && tab !== "ppt") tab = "latex";
    activeTab = tab;
    $(".tab-btn").removeClass("active");
    $('.tab-btn[data-tab="' + tab + '"]').addClass("active");
    if (inputCollapsed) {
      $("#viewLatex, #viewPpt").addClass("active").show();
      $(".latex-actions, .ppt-actions").show();
      refreshEditorSize();
      return;
    }
    if (tab === "latex") {
      $("#viewLatex").addClass("active").show();
      $("#viewPpt").removeClass("active").hide();
      $(".latex-actions").show();
      $(".ppt-actions").hide();
    } else {
      $("#viewPpt").addClass("active").show();
      $("#viewLatex").removeClass("active").hide();
      $(".latex-actions").hide();
      $(".ppt-actions").show();
    }
  }

  $("#btnToggleInputPanel").on("click", function (event) {
    event.preventDefault();
    event.stopPropagation();
    inputCollapsed = !inputCollapsed;
    localStorage.setItem("bg_input_panel_collapsed", inputCollapsed ? "1" : "0");
    applyInputCollapsedState();
  });

  $(".tab-btn").on("click", function () {
    if ($(this).prop("disabled")) return;
    var tab = $(this).data("tab");
    if (tab === activeTab) return;
    setActiveTab(tab);
  });

  $("#btnGenerate").on("click", function () {
    if (isGenerating) return;

    var content = $("#content").val().trim();
    if (!content) {
      setStatus("请先导入 .md/.markdown 知识图谱文件", "error");
      return;
    }

    var previousLatex = fullLatex;
    var generatedLatex = "";
    var receivedFirstChunk = false;
    currentCustomRequirements = $("#customRequirements").val().trim();
    $("#tabPpt").prop("disabled", true);
    setGenerating(true);
    updateLatexGenerateProgress(5, "正在使用网站统一 DeepSeek 配置生成 LaTeX...");

    var payload = {
      content: content,
      style: $("#style").val(),
      custom_requirements: currentCustomRequirements,
      slide_count: Math.max(25, parseInt($("#slideCount").val(), 10) || 25),
      language: $("#language").val(),
      figure_assets: buildFigureAssetPayload(),
    };

    var generateTimeoutMs = 300000;
    var abortCtrl = new AbortController();
    var timeoutId = setTimeout(function () {
      abortCtrl.abort();
      setGenerating(false);
      setStatus("生成超时，5 分钟无新数据", "error");
    }, generateTimeoutMs);

    function resetTimeout() {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(function () {
        abortCtrl.abort();
        setGenerating(false);
      setStatus("生成超时，5 分钟无新数据", "error");
      }, generateTimeoutMs);
    }

    fetch("/beamer-generator/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: abortCtrl.signal,
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        resetTimeout();
        updateLatexGenerateProgress(12, "已连接 DeepSeek，正在等待生成...");
        var reader = resp.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";

        function pump() {
          return reader.read().then(function (r) {
              if (r.done) {
                if (isGenerating) {
                  if (!receivedFirstChunk) {
                    setGenerating(false);
                    fullLatex = previousLatex;
                    updateLatexEditor(previousLatex);
                    setStatus("DeepSeek 未返回内容，请检查 API Key、Base URL、模型名或网络", "error");
                  } else {
                    updateLatexGenerateProgress(100, "生成完成，共 " + fullLatex.length + " 字符");
                    setGenerating(false);
                    fullLatex = applyCustomRequirementOverrides(generatedLatex, currentCustomRequirements);
                    sourceLatex = fullLatex;
                    updateLatexEditor(fullLatex);
                    setStatus("生成完成，共 " + fullLatex.length + " 字符", "success");
                  }
                }
                return;
              }

            buffer += decoder.decode(r.value, { stream: true });
            resetTimeout();

            var lines = buffer.split("\n");
            buffer = lines.pop();

            for (var i = 0; i < lines.length; i++) {
              var line = lines[i].trim();
              if (!line.startsWith("data: ")) continue;
              var d;
              try {
                d = JSON.parse(line.substring(6));
              } catch (e) {
                continue;
              }

              if (d.type === "heartbeat") {
                updateLatexGenerateProgress(Math.max(latexGenerateProgress, 18), "已连接，等待 DeepSeek 生成...");
              } else if (d.type === "chunk") {
                if (!receivedFirstChunk) {
                  receivedFirstChunk = true;
                  generatedLatex = "";
                  fullLatex = "";
                  updateLatexEditor("");
                }
                generatedLatex += d.content;
                fullLatex = generatedLatex;
                updateLatexEditor(fullLatex);
                var estimatedProgress = 25 + Math.min(68, Math.floor(fullLatex.length / 90));
                if (estimatedProgress < latexGenerateProgress) estimatedProgress = latexGenerateProgress;
                updateLatexGenerateProgress(estimatedProgress, "生成中... (" + fullLatex.length + " 字符)");
              } else if (d.type === "done") {
                clearTimeout(timeoutId);
                if (!receivedFirstChunk) {
                  setGenerating(false);
                  fullLatex = previousLatex;
                  updateLatexEditor(previousLatex);
                  setStatus("DeepSeek 未返回内容，请检查 API Key、Base URL、模型名或网络", "error");
                  return;
                }
                fullLatex = applyCustomRequirementOverrides(generatedLatex, currentCustomRequirements);
                sourceLatex = fullLatex;
                updateLatexEditor(fullLatex);
                updateLatexGenerateProgress(100, "生成完成，共 " + fullLatex.length + " 字符");
                setGenerating(false);
                setStatus("生成完成，共 " + fullLatex.length + " 字符", "success");
                return;
              } else if (d.type === "error") {
                clearTimeout(timeoutId);
                setGenerating(false);
                setStatus("Error: " + d.content, "error");
                return;
              }
            }

            return pump();
          });
        }

        return pump();
      })
      .catch(function (err) {
        clearTimeout(timeoutId);
        setGenerating(false);
        if (err.name === "AbortError") return;
        setStatus("生成请求失败: " + err.message, "error");
      });
  });

  $("#btnCopy").on("click", function () {
    if (!fullLatex) return;
    if (slidesData && $("#slideCanvas").find(":focus").length) {
      saveCurrentSlide();
      syncLatexFromSlides();
    } else if (editor && editor.getValue) {
      fullLatex = editor.getValue();
      sourceLatex = fullLatex;
    }
    if (navigator.clipboard) {
      navigator.clipboard.writeText(fullLatex).then(function () {
        setStatus("操作完成", "success");
      });
    } else {
      var $t = $("<textarea>").appendTo("body").val(fullLatex).select();
      document.execCommand("copy");
      $t.remove();
      setStatus("操作完成", "success");
    }
  });

  $("#btnDownloadTex").on("click", function () {
    if (!fullLatex) return;
    if (slidesData && $("#slideCanvas").find(":focus").length) {
      saveCurrentSlide();
      syncLatexFromSlides();
    } else if (editor && editor.getValue) {
      fullLatex = editor.getValue();
      sourceLatex = fullLatex;
    }
    downloadFile(fullLatex, "presentation_" + today() + ".tex", "application/x-tex");
    setStatus("操作完成", "success");
  });

  $(document).on("click", "#btnUndoPpt", function () {
    undoPptEdit();
  });

  $(document).on("click", "#btnRedoPpt", function () {
    redoPptEdit();
  });

  $("#btnConvertPpt").on("click", function () {
    if (editor && editor.getValue) {
      fullLatex = editor.getValue();
      sourceLatex = fullLatex;
    }
    if (!fullLatex) return;
    setStatus("正在解析 LaTeX 结构...", "info");

    $.ajax({
      url: "/beamer-generator/api/parse-slides",
      method: "POST",
      contentType: "application/json",
      data: JSON.stringify({ latex: fullLatex }),
      success: function (data) {
        if (data.error) {
          setStatus("解析失败: " + data.error, "error");
          return;
        }

        for (var i = 0; i < data.slides.length; i++) {
          if (!data.slides[i].images) data.slides[i].images = [];
          if (!data.slides[i].textboxes) data.slides[i].textboxes = [];
          if (!data.slides[i].callouts) data.slides[i].callouts = [];
          normalizeSlideEditableText(data.slides[i]);
          data.slides[i].placeholders = normalizePlaceholders(data.slides[i].placeholders);
          if (data.slides[i].table) data.slides[i].table = normalizeTable(data.slides[i].table);
        }
        ensureAllSlideFigurePlaceholders(data);

        slidesData = data;
        $("#pptChapterTitleInput").val("");
        sourceLatex = fullLatex;
        fullLatex = buildLatexFromSlides(slidesData);
        sourceLatex = fullLatex;
        updateLatexEditor(fullLatex);
        currentSlideIdx = data.slides.length > 0 ? 0 : -1;
        resetHistory();
        $("#tabPpt").prop("disabled", false);
        updateDownloadPptxButton();
        setStatus("解析完成，共 " + data.slides.length + " 页幻灯片", "success");
        setActiveTab("ppt");
        renderSlideList();
        if (currentSlideIdx >= 0) selectSlide(currentSlideIdx);
      },
      error: function () {
        setStatus("解析请求失败", "error");
      },
    });
  });

  function slideThumbBoxStyle(box, fallback) {
    box = box || {};
    fallback = fallback || {};
    var width = clampNumber(Number(box.width), 40, SLIDE_DESIGN_WIDTH, Number(fallback.width) || 220);
    var height = clampNumber(Number(box.height), 28, SLIDE_DESIGN_HEIGHT, Number(fallback.height) || 140);
    var x = clampNumber(Number(box.x), 0, Math.max(0, SLIDE_DESIGN_WIDTH - width), Number(fallback.x) || 40);
    var y = clampNumber(Number(box.y), 0, Math.max(0, SLIDE_DESIGN_HEIGHT - height), Number(fallback.y) || 170);
    return [
      "left:" + (x / SLIDE_DESIGN_WIDTH * 100).toFixed(2) + "%",
      "top:" + (y / SLIDE_DESIGN_HEIGHT * 100).toFixed(2) + "%",
      "width:" + (width / SLIDE_DESIGN_WIDTH * 100).toFixed(2) + "%",
      "height:" + (height / SLIDE_DESIGN_HEIGHT * 100).toFixed(2) + "%"
    ].join(";");
  }

  function renderSlideThumbPreview(slide, pageIndex) {
    slide = slide || {};
    var items = Array.isArray(slide.items) ? slide.items.slice(0, 4) : [];
    var equations = Array.isArray(slide.equations) ? slide.equations.slice(0, 1) : [];
    var placeholders = Array.isArray(slide.placeholders) ? slide.placeholders.slice(0, 4) : [];
    var images = Array.isArray(slide.images) ? slide.images.slice(0, 4) : [];
    var textboxes = Array.isArray(slide.textboxes) ? slide.textboxes.slice(0, 4) : [];
    var callouts = Array.isArray(slide.callouts) ? slide.callouts.slice(0, 3) : [];
    var hasVisibleContent = items.length || equations.length || placeholders.length || images.length ||
      textboxes.length || callouts.length || (slide.table && slide.table.headers);
    var html = '<div class="slide-thumb-preview' + (slide.reviewBackground ? " review-background" : "") + '">' +
      '<div class="slide-thumb-preview-topline"></div>' +
      '<div class="slide-thumb-preview-page">' + (pageIndex + 1) + '</div>' +
      '<div class="slide-thumb-preview-title">' + escHtml(slide.title || "(Untitled)") + '</div>';
    if (slide.subtitle) {
      html += '<div class="slide-thumb-preview-subtitle">' + escHtml(String(slide.subtitle).slice(0, 80)) + '</div>';
    }
    html += '<div class="slide-thumb-preview-content">';
    if (items.length) {
      html += '<ul>';
      items.forEach(function (item) {
        html += '<li>' + escHtml(String(item || "").replace(/\s+/g, " ").slice(0, 90)) + '</li>';
      });
      html += '</ul>';
    }
    if (equations.length) {
      html += '<div class="slide-thumb-preview-equation">' + escHtml(String(equations[0] || "").slice(0, 80)) + '</div>';
    }
    if (slide.table && slide.table.headers) {
      html += '<div class="slide-thumb-preview-table"><span></span><span></span><span></span></div>';
    }
    if (!hasVisibleContent) {
      html += '<div class="slide-thumb-preview-empty">空白页</div>';
    }
    html += '</div>';

    placeholders.forEach(function (ph, phIdx) {
      ph = ph || {};
      var phUrl = ph.asset || ph.url || ph.path || "";
      var phStyle = slideThumbBoxStyle(ph, { x: 500 + phIdx * 12, y: 120 + phIdx * 12, width: 235, height: 165 });
      if (phUrl) {
        html += '<img class="slide-thumb-preview-image" style="' + phStyle + '" src="' + escAttr(phUrl) + '" alt="" />';
      } else {
        html += '<div class="slide-thumb-preview-placeholder" style="' + phStyle + '">' +
          escHtml(String(ph.label || ph.figure || "Figure").slice(0, 28)) + '</div>';
      }
    });
    images.forEach(function (img, imgIdx) {
      img = img || {};
      var imgUrl = img.url || img.path || img.src || "";
      if (!imgUrl) return;
      var imgStyle = slideThumbBoxStyle(img, { x: 40 + imgIdx * 16, y: 170 + imgIdx * 12, width: 220, height: 150 });
      html += '<img class="slide-thumb-preview-image" style="' + imgStyle + '" src="' + escAttr(imgUrl) + '" alt="" />';
    });
    textboxes.forEach(function (tb, tbIdx) {
      tb = tb || {};
      var tbStyle = slideThumbBoxStyle(tb, { x: 120 + tbIdx * 14, y: 210 + tbIdx * 12, width: 260, height: 70 });
      var fontSize = Math.max(5, Math.min(9, (Number(tb.fontSize) || 14) * 0.45));
      html += '<div class="slide-thumb-preview-textbox" style="' + tbStyle + ';font-size:' + fontSize.toFixed(1) + 'px">' +
        escHtml(String(tb.text || "").replace(/\s+/g, " ").slice(0, 70)) + '</div>';
    });
    callouts.forEach(function (callout, calloutIdx) {
      callout = callout || {};
      var calloutStyle = slideThumbBoxStyle(callout, { x: 130 + calloutIdx * 18, y: 178 + calloutIdx * 18, width: 250, height: 92 });
      html += '<div class="slide-thumb-preview-callout" style="' + calloutStyle + '">' +
        escHtml(String(callout.text || "").replace(/\s+/g, " ").slice(0, 38)) + '</div>';
    });
    html += '</div>';
    return html;
  }

  function renderSlideList() {
    var $list = $("#slideList").empty();
    if (!slidesData || !slidesData.slides) return;

    function appendSavedSlideDropzone(insertIndex) {
      var $zone = $(
        '<div class="slide-insert-dropzone" data-insert-index="' + insertIndex + '" title="拖拽已保存页面到这里插入"></div>'
      );

      $zone.on("dragover", function (e) {
        if (!savedSlideDragPayload) return;
        e.preventDefault();
        e.stopPropagation();
        $zone.addClass("active");
        if (e.originalEvent && e.originalEvent.dataTransfer) {
          e.originalEvent.dataTransfer.dropEffect = "copy";
        }
      });

      $zone.on("dragleave", function () {
        $zone.removeClass("active");
      });

      $zone.on("drop", function (e) {
        if (!savedSlideDragPayload) return;
        e.preventDefault();
        e.stopPropagation();
        var payload = savedSlideDragPayload;
        var targetIndex = parseInt($zone.attr("data-insert-index"), 10);
        savedSlideDragPayload = null;
        $(".slide-insert-dropzone").removeClass("active");
        loadSavedSlideFromProject(payload.projectIndex, payload.pageIndex)
          .then(function (slide) {
            if (!slidesData) throw new Error("当前没有可编辑的 PPT");
            insertSavedSlideIntoCurrentProject(slide, targetIndex);
          })
          .catch(function (err) {
            setStatus("拖拽插入失败: " + err.message, "error");
          });
      });

      $list.append($zone);
    }

    var typeNames = { title: "Title", toc: "TOC", content: "Content" };
    for (var i = 0; i < slidesData.slides.length; i++) {
      (function (idx) {
        appendSavedSlideDropzone(idx);
        var s = slidesData.slides[idx];
        var $thumb = $(
          '<div class="slide-thumb" draggable="true" data-idx="' + idx + '" title="按住拖动可调整页面顺序">' +
            '<button class="slide-thumb-delete" title="Delete">&times;</button>' +
            renderSlideThumbPreview(s, idx) +
            '<div class="slide-thumb-meta">' +
              '<span class="slide-thumb-number">Page ' + (idx + 1) + '</span>' +
              '<span class="slide-thumb-type">' + (typeNames[s.type] || "Content") + '</span>' +
            '</div>' +
          '</div>'
        );

        $thumb.on("click", function (e) {
          if ($(e.target).hasClass("slide-thumb-delete")) return;
          selectSlide(idx);
        });

        $thumb.find(".slide-thumb-delete").on("click", function (e) {
          e.stopPropagation();
          deleteSlide(idx);
        });

        $thumb.on("dragstart", function (e) {
          if ($(e.target).hasClass("slide-thumb-delete")) {
            e.preventDefault();
            return;
          }
          slideThumbDragIndex = idx;
          $thumb.addClass("dragging");
          if (e.originalEvent && e.originalEvent.dataTransfer) {
            e.originalEvent.dataTransfer.effectAllowed = "move";
            e.originalEvent.dataTransfer.setData("text/plain", "slide-thumb:" + idx);
          }
        });

        $thumb.on("dragover", function (e) {
          if (slideThumbDragIndex === null || slideThumbDragIndex === idx) return;
          e.preventDefault();
          $thumb.addClass("drag-over");
          if (e.originalEvent && e.originalEvent.dataTransfer) {
            e.originalEvent.dataTransfer.dropEffect = "move";
          }
        });

        $thumb.on("dragleave", function () {
          $thumb.removeClass("drag-over");
        });

        $thumb.on("drop", function (e) {
          if (slideThumbDragIndex === null) return;
          e.preventDefault();
          e.stopPropagation();
          reorderSlides(slideThumbDragIndex, idx);
          slideThumbDragIndex = null;
        });

        $thumb.on("dragend", function () {
          slideThumbDragIndex = null;
          $(".slide-thumb").removeClass("dragging drag-over");
        });

        $list.append($thumb);
      })(i);
    }
    appendSavedSlideDropzone(slidesData.slides.length);

    if (currentSlideIdx >= 0) {
      $list.find(".slide-thumb").eq(currentSlideIdx).addClass("active");
    }
  }

  function reorderSlides(fromIdx, toIdx) {
    if (!slidesData || !Array.isArray(slidesData.slides)) return;
    if (fromIdx === toIdx) return;
    if (fromIdx < 0 || fromIdx >= slidesData.slides.length) return;
    if (toIdx < 0 || toIdx >= slidesData.slides.length) return;
    saveCurrentSlide();
    var moved = slidesData.slides.splice(fromIdx, 1)[0];
    slidesData.slides.splice(toIdx, 0, moved);
    for (var i = 0; i < slidesData.slides.length; i++) {
      slidesData.slides[i].id = i;
    }
    if (currentSlideIdx === fromIdx) {
      currentSlideIdx = toIdx;
    } else if (fromIdx < currentSlideIdx && toIdx >= currentSlideIdx) {
      currentSlideIdx -= 1;
    } else if (fromIdx > currentSlideIdx && toIdx <= currentSlideIdx) {
      currentSlideIdx += 1;
    }
    renderSlideList();
    if (currentSlideIdx >= 0 && slidesData.slides[currentSlideIdx]) {
      renderSlideEditor(slidesData.slides[currentSlideIdx]);
      selectLatexSyncForSlide(currentSlideIdx);
    }
    syncLatexFromSlides();
    commitHistorySnapshot(false);
    setStatus("页面顺序已调整，点击保存后会按新顺序保存", "success");
  }

  function selectSlide(idx) {
    if (!slidesData || idx < 0 || idx >= slidesData.slides.length) return;
    saveCurrentSlide();
    commitHistorySnapshot(false);
    currentSlideIdx = idx;
    $(".slide-thumb").removeClass("active").eq(idx).addClass("active");
    renderSlideEditor(slidesData.slides[idx]);
    selectLatexSyncForSlide(idx);
  }

  function renderSlideEditor(slide) {
    var $canvas = $("#slideCanvas").empty();
    applyEditedGeometryToSlide(slide, currentSlideIdx);
    normalizeSlideEditableText(slide);
    if (!slide.textboxes) slide.textboxes = [];
    if (!slide.images) slide.images = [];
    if (!slide.callouts) slide.callouts = [];
    normalizeSlideEquations(slide);
    slide.placeholders = normalizePlaceholders(slide.placeholders);
    ensureSlideFigurePlaceholders(slide);
    if (slide.table) slide.table = normalizeTable(slide.table);

    var $left = $('<div class="slide-main-area"></div>');
    var $render = $('<div class="slide-render' + (slide.reviewBackground ? " review-background" : "") + '" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "frame")) + '"></div>');
    $render.append('<div class="slide-topline"></div>');

    $render.append(
      '<div class="slide-title-bar slide-formula-host">' +
        '<input class="slide-title-input slide-hidden-math-source" data-field="title" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "title")) + '" value="' +
        escAttr(slide.title || "") + '" placeholder="输入标题..." />' +
      '</div>'
    );

    $render.append(
      '<div class="slide-subtitle-bar slide-formula-host">' +
        '<input class="slide-subtitle-input slide-hidden-math-source" data-field="subtitle" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "subtitle")) + '" value="' +
        escAttr(slide.subtitle || "") + '" placeholder="副标题（可选）" />' +
      '</div>'
    );

    $render.find(".slide-title-bar").append(
      '<div class="slide-title-input slide-title-rich slide-rich-text-preview" contenteditable="true" spellcheck="false" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "title")) + '" data-math-source=".slide-title-input" data-rich-html="' + escAttr(slide.titleRichHtml || "") + '"></div>'
    );
    $render.find(".slide-subtitle-bar").append(
      '<div class="slide-subtitle-input slide-subtitle-rich slide-rich-text-preview" contenteditable="true" spellcheck="false" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "subtitle")) + '" data-math-source=".slide-subtitle-input" data-rich-html="' + escAttr(slide.subtitleRichHtml || "") + '"></div>'
    );

    var $body = $('<div class="slide-body"></div>');
    var hasRightPlaceholder = (slide.placeholders || []).some(function (ph) {
      var x = parseFloat(ph && ph.x) || 0;
      return x >= 430;
    });
    if (hasRightPlaceholder) {
      $body.addClass("has-right-figure");
    }

    if (slide.items && slide.items.length > 0) {
      var $items = $('<ul class="slide-items-list"></ul>');
      $.each(slide.items, function (j, item) {
        $items.append(createItemRow(j, item));
      });
      $body.append($items);
    } else {
      $body.append('<ul class="slide-items-list"></ul>');
    }

    if (slide.equations && slide.equations.length > 0) {
      var $eqs = $('<div class="slide-equations"></div>');
      $.each(slide.equations, function (j, eq) {
        var key = syncKey(currentSlideIdx, "equation", j);
        $eqs.append(
          '<div class="slide-equation-row" data-math-row data-sync-key="' + escAttr(key) + '">' +
            '<input class="slide-eq-input slide-hidden-math-source" data-sync-key="' + escAttr(key) + '" data-eq="' + j +
        '" value="' + escAttr(eq) + '" placeholder="LaTeX 公式..." />' +
            '<div class="slide-math-preview" data-sync-key="' + escAttr(key) + '" data-math-source=".slide-eq-input" data-math-display="true"></div>' +
          '</div>'
        );
      });
      $body.append($eqs);
    }

    if (slide.table && slide.table.headers) {
      $body.append(renderEditableTable(slide.table));
    }

    var $textboxes = $('<div class="slide-textboxes slide-free-layer"></div>');
    $.each(slide.placeholders, function (j, ph) {
      $textboxes.append(createImagePlaceholder(j, ph));
    });
    $.each(slide.textboxes, function (j, tb) {
      $textboxes.append(createTextbox(j, tb));
    });
    $.each(slide.callouts, function (j, callout) {
      $textboxes.append(createCallout(j, callout));
    });
    $render.append($textboxes);

    var $images = $('<div class="slide-images"></div>');
    $.each(slide.images, function (j, img) {
      $images.append(createImageItem(j, img));
    });

    $render.append($body);
    $render.append($images);
    $left.append($render);

    $left.append(
      '<div class="slide-notes-section">' +
        '<div class="slide-notes-label">备注 / 演讲稿</div>' +
        '<textarea class="slide-notes-input" data-field="notes" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "notes")) + '" placeholder="添加演讲备注...">' +
        escHtml(slide.notes || "") + '</textarea>' +
      '</div>'
    );

    $canvas.append($left);
    $canvas.find(".slide-title-bar").append(
      '<div class="slide-formula-boxes slide-title-formulas" data-formula-source=".slide-title-input"></div>'
    );
    $canvas.find(".slide-subtitle-bar").append(
      '<div class="slide-formula-boxes slide-subtitle-formulas" data-formula-source=".slide-subtitle-input"></div>'
    );
    $canvas.find(".slide-notes-section").append(
      '<div class="slide-formula-boxes slide-notes-formulas" data-formula-source=".slide-notes-input"></div>'
    );

    $canvas.append(
        '<div class="slide-toolbar">' +
        '<div class="toolbar-label">操作</div>' +
        '<button id="btnUndoPpt" class="toolbar-btn ppt-history-btn" disabled>撤销</button>' +
        '<button id="btnRedoPpt" class="toolbar-btn ppt-history-btn" disabled>重做</button>' +
        '<div class="toolbar-sep"></div>' +
        '<div class="toolbar-label">插入</div>' +
        '<button class="toolbar-btn" data-action="add-item">+ 要点</button>' +
        '<button class="toolbar-btn" data-action="add-textbox">+ 文本框</button>' +
        '<button class="toolbar-btn" data-action="add-callout">蓝色箭头框</button>' +
        '<button class="toolbar-btn" data-action="insert-image">+ 图片</button>' +
        '<button class="toolbar-btn review-background-tool" data-action="apply-review-background"><span>复习页面背景</span><span class="review-background-popover" aria-hidden="true"></span></button>' +
        '<div class="toolbar-sep"></div>' +
        '<div class="toolbar-label">文字</div>' +
        '<div class="toolbar-color">' +
          '<label>颜色</label>' +
          '<input type="color" id="toolbarFontColor" value="#333333" />' +
        '</div>' +
        '<div class="toolbar-color">' +
          '<label>背景</label>' +
          '<input type="color" id="toolbarBgColor" value="#ffffff" />' +
          '<button id="toolbarResetBgColor" class="toolbar-btn toolbar-mini toolbar-reset-btn" type="button" title="恢复白色背景">白底</button>' +
        '</div>' +
        '<div class="toolbar-sep"></div>' +
        '<div class="toolbar-label">字号</div>' +
        '<select id="toolbarFontSize">' +
          '<option value="12">12</option>' +
          '<option value="14" selected>14</option>' +
          '<option value="16">16</option>' +
          '<option value="18">18</option>' +
          '<option value="20">20</option>' +
          '<option value="24">24</option>' +
        '</select>' +
        '<select id="toolbarTextAlign">' +
          '<option value="left">左对齐</option>' +
          '<option value="center">居中</option>' +
          '<option value="right">右对齐</option>' +
        '</select>' +
        '<div class="toolbar-row">' +
          '<button class="toolbar-btn toolbar-mini" data-action="toggle-bold">B</button>' +
          '<button class="toolbar-btn toolbar-mini" data-action="toggle-italic"><i>I</i></button>' +
        '</div>' +
      '</div>'
    );

    bindToolbarEvents($canvas);
    bindSlideEvents($canvas);
    updateHistoryButtons();
    updateScopedMathPreviews($canvas);
  }

  function createItemRow(idx, text) {
    var key = syncKey(currentSlideIdx, "item", idx);
    return $(
      '<li class="slide-item-row">' +
        '<span class="slide-item-bullet">&#8226;</span>' +
        '<div class="slide-item-content" data-math-row data-sync-key="' + escAttr(key) + '">' +
          '<textarea class="slide-item-input slide-hidden-math-source" data-sync-key="' + escAttr(key) + '" data-item="' + idx +
          '" placeholder="输入要点内容...">' + escHtml(text || "") + '</textarea>' +
          '<div class="slide-formula-boxes" data-formula-source=".slide-item-input"></div>' +
          '<div class="slide-math-preview slide-rich-text-preview" contenteditable="true" spellcheck="false" data-sync-key="' + escAttr(key) + '" data-math-source=".slide-item-input" data-rich-html="' + escAttr((slidesData.slides[currentSlideIdx].itemRichHtml || [])[idx] || "") + '"></div>' +
        '</div>' +
        '<button class="slide-item-remove" data-action="remove-item" data-item="' +
        idx + '">&times;</button>' +
      '</li>'
    );
  }

  function placeholderGeometryKey(slideIdx, idx, ph) {
    var figureKey = normalizeFigureLabel((ph && (ph.figure || ph.label)) || "");
    return slideIdx + ":" + (figureKey || ("placeholder-" + idx));
  }

  function imageGeometryKey(slideIdx, idx, img) {
    var path = String((img && img.path) || "").trim();
    return slideIdx + ":" + (path || ("image-" + idx));
  }

  function rememberPlaceholderGeometry(slideIdx, idx, ph) {
    if (!ph) return;
    editedImageGeometry.placeholders[placeholderGeometryKey(slideIdx, idx, ph)] = {
      x: ph.x,
      y: ph.y,
      width: ph.width,
      height: ph.height,
    };
  }

  function rememberImageGeometry(slideIdx, idx, img) {
    if (!img) return;
    editedImageGeometry.images[imageGeometryKey(slideIdx, idx, img)] = {
      x: img.x,
      y: img.y,
      width: img.width,
      height: img.height,
    };
  }

  function applyEditedGeometryToSlide(slide, slideIdx) {
    if (!slide) return;
    if (slide.placeholders && slide.placeholders.length) {
      slide.placeholders = normalizePlaceholders(slide.placeholders);
      slide.placeholders.forEach(function (ph, idx) {
        var saved = editedImageGeometry.placeholders[placeholderGeometryKey(slideIdx, idx, ph)];
        if (!saved) return;
        ph.x = saved.x;
        ph.y = saved.y;
        ph.width = saved.width;
        ph.height = saved.height;
      });
    }
    if (slide.images && slide.images.length) {
      slide.images.forEach(function (img, idx) {
        var saved = editedImageGeometry.images[imageGeometryKey(slideIdx, idx, img)];
        if (!saved) return;
        img.x = saved.x;
        img.y = saved.y;
        img.width = saved.width;
        img.height = saved.height;
      });
    }
  }

  function savePlaceholderGeometry(idx, $box) {
    if (!slidesData || currentSlideIdx < 0 || !$box || !$box.length) return;
    var slide = slidesData.slides[currentSlideIdx];
    if (!slide) return;
    slide.placeholders = normalizePlaceholders(slide.placeholders);
    if (!slide.placeholders[idx]) return;
    var renderScale = slideScale($("#slideCanvas .slide-render").first());
    slide.placeholders[idx].x = fromSlidePx(parseFloat($box.css("left")) || 0, renderScale);
    slide.placeholders[idx].y = fromSlidePx(parseFloat($box.css("top")) || 0, renderScale);
    slide.placeholders[idx].width = fromSlidePx(cssPx($box, "width", 245), renderScale);
    slide.placeholders[idx].height = fromSlidePx(cssPx($box, "height", 230), renderScale);
    rememberPlaceholderGeometry(currentSlideIdx, idx, slide.placeholders[idx]);
  }

  function saveImageGeometry(idx, $item) {
    if (!slidesData || currentSlideIdx < 0 || !$item || !$item.length) return;
    var slide = slidesData.slides[currentSlideIdx];
    if (!slide || !slide.images || !slide.images[idx]) return;
    var renderScale = slideScale($("#slideCanvas .slide-render").first());
    slide.images[idx].x = fromSlidePx(parseFloat($item.css("left")) || 0, renderScale);
    slide.images[idx].y = fromSlidePx(parseFloat($item.css("top")) || 0, renderScale);
    slide.images[idx].width = fromSlidePx(cssPx($item, "width", 220), renderScale);
    slide.images[idx].height = fromSlidePx(cssPx($item, "height", 150), renderScale);
    rememberImageGeometry(currentSlideIdx, idx, slide.images[idx]);
  }

  function createImagePlaceholder(idx, ph) {
    ph = normalizePlaceholders([ph])[0];
    var key = syncKey(currentSlideIdx, "placeholder", idx);
    var scale = slideScale($("#slideCanvas .slide-render").first());
    var left = toSlidePx(ph.x, scale);
    var top = toSlidePx(ph.y, scale);
    var width = toSlidePx(ph.width, scale);
    var height = toSlidePx(ph.height, scale);
    var figureRef = extractFigureReference(ph.figure || ph.label || "");
    var figureKey = normalizeFigureLabel(figureRef);
    var figure = figurePreviewMap[figureKey] || null;
    var figureUrl = ph.asset || (figure && figure.url) || pickPackageImageForFigure(figureRef);
    var previewHtml = figureUrl
      ? '<img class="slide-placeholder-preview" src="' + escAttr(figureUrl) + '" alt="' + escAttr(figureRef || ph.label || "image") + '" />'
      : '<div class="slide-placeholder-icon">+</div>';
    var $box = $(
      '<div class="slide-image-placeholder' + (figureUrl ? " has-image" : "") + '" data-sync-key="' + escAttr(key) + '" data-ph="' + idx + '" data-figure="' + escAttr(figureRef) + '" data-asset="' + escAttr(figureUrl) + '" style="left:' + left + 'px;top:' + top + 'px;width:' + width + 'px;height:' + height + 'px;">' +
        '<div class="slide-placeholder-drag" title="拖动占位框">::</div>' +
        previewHtml +
        '<input class="slide-placeholder-label" data-sync-key="' + escAttr(key) + '" data-ph-label="' + idx + '" value="' + escAttr(ph.label || "图片占位") + '" />' +
        '<button class="slide-placeholder-remove" data-action="remove-placeholder" data-ph="' + idx + '">&times;</button>' +
        '<div class="slide-placeholder-resize-handle"></div>' +
      '</div>'
    );

    $box.on("mousedown", function (e) {
      if ($(e.target).is(".slide-placeholder-label, .slide-placeholder-remove, .slide-placeholder-resize-handle")) return;
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origX = parseFloat($box.css("left")) || 0;
      var origY = parseFloat($box.css("top")) || 0;
      $box.addClass("dragging");

      $(document).on("mousemove.phdrag", function (e2) {
        var parentW = $box.parent().width() || 860;
        var parentH = $box.parent().height() || 484;
        var boxW = cssPx($box, "width", $box.outerWidth());
        var boxH = cssPx($box, "height", $box.outerHeight());
        var nextX = clampNumber(origX + (e2.clientX - startX), 0, parentW - boxW, 0);
        var nextY = clampNumber(origY + (e2.clientY - startY), 0, parentH - boxH, 0);
        $box.css({ left: nextX + "px", top: nextY + "px" });
      });
      $(document).on("mouseup.phdrag", function () {
        $box.removeClass("dragging");
        $(document).off("mousemove.phdrag mouseup.phdrag");
        savePlaceholderGeometry(idx, $box);
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    $box.find(".slide-placeholder-resize-handle").on("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origW = cssPx($box, "width", $box.outerWidth());
      var origH = cssPx($box, "height", $box.outerHeight());

      $(document).on("mousemove.phresize", function (e2) {
        var parentW = $box.parent().width() || 860;
        var parentH = $box.parent().height() || 484;
        var left = parseFloat($box.css("left")) || 0;
        var top = parseFloat($box.css("top")) || 0;
        var newW = Math.min(parentW - left, Math.max(80, origW + (e2.clientX - startX)));
        var newH = Math.min(parentH - top, Math.max(60, origH + (e2.clientY - startY)));
        $box.css({ width: newW + "px", height: newH + "px" });
      });
      $(document).on("mouseup.phresize", function () {
        $(document).off("mousemove.phresize mouseup.phresize");
        savePlaceholderGeometry(idx, $box);
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    return $box;
  }

  function createTextbox(idx, tb) {
    tb = tb || {};
    var key = syncKey(currentSlideIdx, "textbox", idx);
    var color = toCssColor(tb.color, "#333333");
    var bg = toCssColor(tb.bg, "");
    var fontSize = clampNumber(tb.fontSize, 10, 48, 14);
    var align = tb.align || "left";
    var bold = !!tb.bold;
    var italic = !!tb.italic;
    var richHtml = tb.richHtml || "";
    var style = "";
    if (color) style += "color:" + color + ";";
    if (bg && bg !== "rgba(0, 0, 0, 0)") style += "background:" + bg + ";";
    if (fontSize) style += "font-size:" + fontSize + "px;";
    style += "text-align:" + align + ";";
    if (bold) style += "font-weight:700;";
    if (italic) style += "font-style:italic;";

    var width = clampNumber(tb.width, 100, 780, 260);
    var height = clampNumber(tb.height, 40, 360, 96);
    var x = clampNumber(tb.x, 0, 760, 40 + idx * 18);
    var y = clampNumber(tb.y, 0, 430, 190 + idx * 22);
    var boxStyle = "left:" + x + "px;top:" + y + "px;width:" + width + "px;height:" + height + "px;";
    if (bg && bg !== "rgba(0, 0, 0, 0)") boxStyle += "background:" + bg + ";";
    var $box = $(
      '<div class="slide-textbox" data-sync-key="' + escAttr(key) + '" data-tb="' + idx + '" style="' + boxStyle + '">' +
        '<div class="slide-textbox-drag" title="拖动文本框">::</div>' +
        '<div data-math-row data-sync-key="' + escAttr(key) + '">' +
          '<textarea class="slide-textbox-content slide-hidden-math-source" data-sync-key="' + escAttr(key) + '" style="' + style + '" data-tbcontent="' + idx + '" placeholder="输入文本...">' +
          escHtml(tb.text || "") + '</textarea>' +
          '<div class="slide-formula-boxes" data-formula-source=".slide-textbox-content"></div>' +
          '<div class="slide-math-preview slide-rich-text-preview" contenteditable="true" spellcheck="false" data-sync-key="' + escAttr(key) + '" data-math-source=".slide-textbox-content" data-rich-html="' + escAttr(richHtml) + '"></div>' +
        '</div>' +
        '<button class="slide-textbox-remove" data-action="remove-textbox" data-tb="' + idx + '">&times;</button>' +
        '<div class="slide-textbox-resize-handle" data-action="resize-tb"></div>' +
      '</div>'
    );
    $box.find(".slide-textbox-content").css("height", Math.max(30, height - 18) + "px");

    $box.find(".slide-textbox-drag").on("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origX = parseFloat($box.css("left")) || 0;
      var origY = parseFloat($box.css("top")) || 0;
      $box.addClass("dragging");

      $(document).on("mousemove.tbdrag", function (e2) {
        var parentW = $box.parent().width() || 860;
        var parentH = $box.parent().height() || 484;
        var nextX = clampNumber(origX + (e2.clientX - startX), 0, parentW - 40, 0);
        var nextY = clampNumber(origY + (e2.clientY - startY), 0, parentH - 30, 0);
        $box.css({
          left: nextX + "px",
          top: nextY + "px",
        });
      });
      $(document).on("mouseup.tbdrag", function () {
        $box.removeClass("dragging");
        $(document).off("mousemove.tbdrag mouseup.tbdrag");
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    $box.find(".slide-textbox-resize-handle").on("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origW = $box.outerWidth();
      var origH = $box.outerHeight();

      $(document).on("mousemove.tbresize", function (e2) {
        var newW = Math.max(100, origW + (e2.clientX - startX));
        var newH = Math.max(36, origH + (e2.clientY - startY));
        $box.css({ width: newW + "px", height: newH + "px" });
        $box.find(".slide-textbox-content").css("height", (newH - 20) + "px");
      });
      $(document).on("mouseup.tbresize", function () {
        $(document).off("mousemove.tbresize mouseup.tbresize");
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    return $box;
  }

  function createCallout(idx, callout) {
    callout = callout || {};
    var key = syncKey(currentSlideIdx, "callout", idx);
    var width = clampNumber(callout.width, 120, 760, 250);
    var height = clampNumber(callout.height, 50, 320, 92);
    var x = clampNumber(callout.x, 0, 760, 130 + idx * 18);
    var y = clampNumber(callout.y, 0, 420, 178 + idx * 18);
    var fontSize = clampNumber(callout.fontSize, 8, 28, 12);
    var align = callout.align || "center";
    var $box = $(
      '<div class="slide-callout" data-sync-key="' + escAttr(key) + '" data-callout="' + idx + '" style="left:' + x + 'px;top:' + y + 'px;width:' + width + 'px;height:' + height + 'px;">' +
        '<div class="slide-callout-drag" title="拖动蓝色箭头框">::</div>' +
        '<textarea class="slide-callout-content" data-sync-key="' + escAttr(key) + '" data-callout-content="' + idx + '" style="font-size:' + fontSize + 'px;text-align:' + escAttr(align) + ';" placeholder="输入标注文字...">' +
          escHtml(repairPptLatexArtifacts(callout.text || "蓝色箭头框")) + '</textarea>' +
        '<button class="slide-callout-remove" data-action="remove-callout" data-callout="' + idx + '">&times;</button>' +
        '<div class="slide-callout-resize-handle"></div>' +
      '</div>'
    );
    $box.find(".slide-callout-content").css("height", Math.max(28, height - 18) + "px");

    $box.find(".slide-callout-drag").on("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origX = parseFloat($box.css("left")) || 0;
      var origY = parseFloat($box.css("top")) || 0;
      $box.addClass("dragging");

      $(document).on("mousemove.calloutdrag", function (e2) {
        var parentW = $box.parent().width() || 860;
        var parentH = $box.parent().height() || 484;
        var boxW = cssPx($box, "width", $box.outerWidth());
        var boxH = cssPx($box, "height", $box.outerHeight());
        var nextX = clampNumber(origX + (e2.clientX - startX), 0, parentW - boxW, 0);
        var nextY = clampNumber(origY + (e2.clientY - startY), 0, parentH - boxH, 0);
        $box.css({ left: nextX + "px", top: nextY + "px" });
      });
      $(document).on("mouseup.calloutdrag", function () {
        $box.removeClass("dragging");
        $(document).off("mousemove.calloutdrag mouseup.calloutdrag");
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    $box.find(".slide-callout-resize-handle").on("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origW = cssPx($box, "width", $box.outerWidth());
      var origH = cssPx($box, "height", $box.outerHeight());

      $(document).on("mousemove.calloutresize", function (e2) {
        var parentW = $box.parent().width() || 860;
        var parentH = $box.parent().height() || 484;
        var left = parseFloat($box.css("left")) || 0;
        var top = parseFloat($box.css("top")) || 0;
        var newW = Math.min(parentW - left, Math.max(120, origW + (e2.clientX - startX)));
        var newH = Math.min(parentH - top, Math.max(50, origH + (e2.clientY - startY)));
        $box.css({ width: newW + "px", height: newH + "px" });
        $box.find(".slide-callout-content").css("height", (newH - 18) + "px");
      });
      $(document).on("mouseup.calloutresize", function () {
        $(document).off("mousemove.calloutresize mouseup.calloutresize");
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    return $box;
  }

  function createImageItem(idx, img) {
    img = img || {};
    var scale = slideScale($("#slideCanvas .slide-render").first());
    var x = toSlidePx(img.x || 40, scale);
    var y = toSlidePx(img.y || 170, scale);
    var w = toSlidePx(img.width || 220, scale);
    var h = toSlidePx(img.height || 150, scale);
    var $item = $(
      '<div class="slide-image-item" data-img="' + idx + '" style="left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px;">' +
        '<img src="' + escAttr(img.path || "") + '" alt="image" draggable="false" />' +
        '<button class="slide-image-remove" data-action="remove-image" data-img="' + idx + '">&times;</button>' +
        '<div class="slide-image-resize-handle"></div>' +
      '</div>'
    );

    $item.on("mousedown", function (e) {
      if ($(e.target).hasClass("slide-image-remove") || $(e.target).hasClass("slide-image-resize-handle")) return;
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origLeft = parseFloat($item.css("left")) || 0;
      var origTop = parseFloat($item.css("top")) || 0;
      $item.addClass("dragging");

      $(document).on("mousemove.imgdrag", function (e2) {
        var parentW = $item.parent().width() || 860;
        var parentH = $item.parent().height() || 484;
        var itemW = cssPx($item, "width", $item.outerWidth());
        var itemH = cssPx($item, "height", $item.outerHeight());
        var nextX = clampNumber(origLeft + (e2.clientX - startX), 0, parentW - itemW, 0);
        var nextY = clampNumber(origTop + (e2.clientY - startY), 0, parentH - itemH, 0);
        $item.css({
          left: nextX + "px",
          top: nextY + "px",
        });
      });
      $(document).on("mouseup.imgdrag", function () {
        $item.removeClass("dragging");
        $(document).off("mousemove.imgdrag mouseup.imgdrag");
        saveImageGeometry(idx, $item);
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    $item.find(".slide-image-resize-handle").on("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origW = cssPx($item, "width", $item.outerWidth());
      var origH = cssPx($item, "height", $item.outerHeight());

      $(document).on("mousemove.imgresize", function (e2) {
        var parentW = $item.parent().width() || 860;
        var parentH = $item.parent().height() || 484;
        var left = parseFloat($item.css("left")) || 0;
        var top = parseFloat($item.css("top")) || 0;
        var newW = Math.min(parentW - left, Math.max(60, origW + (e2.clientX - startX)));
        var newH = Math.min(parentH - top, Math.max(45, origH + (e2.clientY - startY)));
        $item.css({ width: newW + "px", height: newH + "px" });
      });
      $(document).on("mouseup.imgresize", function () {
        $(document).off("mousemove.imgresize mouseup.imgresize");
        saveImageGeometry(idx, $item);
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    return $item;
  }

  function renderEditableTable(table) {
    table = normalizeTable(table);
    var html = '<div class="slide-table-wrap">' +
      '<div class="slide-table-tools">' +
        '<button type="button" data-action="add-table-row" title="新增一行">+ 行</button>' +
        '<button type="button" data-action="add-table-col" title="新增一列">+ 列</button>' +
        '<button type="button" data-action="remove-table-row" title="删除最后一行">- 行</button>' +
        '<button type="button" data-action="remove-table-col" title="删除最后一列">- 列</button>' +
        '<button type="button" data-action="remove-table" title="删除当前表格">删除表格</button>' +
      '</div>' +
      '<table class="slide-table"><thead><tr>';
    $.each(table.headers || [], function (j, h) {
      var key = syncKey(currentSlideIdx, "th", j);
      html += '<th>' +
        '<div class="slide-table-rich slide-rich-text-preview" contenteditable="true" spellcheck="false" data-sync-key="' + escAttr(key) + '" data-math-source=".slide-table-source" data-rich-html="' + escAttr((table.headerRichHtml || [])[j] || "") + '"></div>' +
        '<input class="slide-table-source" type="hidden" data-th="' + j + '" value="' + escAttr(h || "") + '" />' +
        '</th>';
    });
    html += "</tr></thead><tbody>";
    $.each(table.rows || [], function (i, row) {
      html += "<tr>";
      $.each(row, function (j, cell) {
        var key = syncKey(currentSlideIdx, "td", i, j);
        html += '<td>' +
          '<div class="slide-table-rich slide-rich-text-preview" contenteditable="true" spellcheck="false" data-sync-key="' + escAttr(key) + '" data-math-source=".slide-table-source" data-rich-html="' + escAttr(((table.rowRichHtml || [])[i] || [])[j] || "") + '"></div>' +
          '<input class="slide-table-source" type="hidden" data-tr="' + i + '" data-tc="' + j + '" value="' + escAttr(cell || "") + '" />' +
          '</td>';
      });
      html += "</tr>";
    });
    html += "</tbody></table></div>";
    return $(html);
  }

  function bindSlideEvents($ctx) {
    $ctx.off("click.slide dblclick.slide mousedown.slide focus.slide blur.slide input.slide change.slide select.sync mouseup.sync keyup.sync");

    $ctx.on("focus.slide", ".slide-item-input, .slide-textbox-content, .slide-callout-content, .slide-eq-input, .slide-title-input, .slide-subtitle-input, .slide-notes-input", function () {
      lastFocusedInput = this;
      lastFocusedTextbox = $(this).closest(".slide-textbox, .slide-callout")[0] || null;
      $(this).closest("[data-math-row]").addClass("is-editing");
      $("#toolbarFontSize").val(parseInt($(this).css("font-size"), 10) || 14);
      $("#toolbarTextAlign").val($(this).css("text-align") || "left");
    });

    $ctx.on("focus.slide mouseup.slide keyup.slide", ".slide-rich-text-preview", function () {
      lastFocusedInput = this;
      lastFocusedTextbox = $(this).closest(".slide-textbox, .slide-callout")[0] || null;
      rememberRichTextSelection(this);
      $("#toolbarFontSize").val(parseInt($(this).css("font-size"), 10) || 14);
      $("#toolbarTextAlign").val($(this).css("text-align") || "left");
    });

    $ctx.on("keyup.slide mouseup.slide pointerup.slide", ".slide-rich-text-preview", function () {
      rememberRichTextSelection(this);
    });

    $ctx.on("mousedown.slide", ".slide-item-input, .slide-textbox-content, .slide-callout-content, .slide-eq-input, .slide-title-input, .slide-subtitle-input, .slide-notes-input, .slide-placeholder-label, [data-th], [data-tr], [data-tc]", function (e) {
      e.stopPropagation();
    });

    $ctx.on("blur.slide", ".slide-item-input, .slide-textbox-content, .slide-callout-content, .slide-eq-input", function () {
      var $row = $(this).closest("[data-math-row]");
      setTimeout(function () {
        if (!$row.find(":focus").length) exitMathEdit($row);
      }, 220);
    });

    $ctx.on("click.slide dblclick.slide", ".slide-math-preview", function (e) {
      e.stopPropagation();
      if (syncSelectionLock) return;
      var key = $(this).data("sync-key");
      if (key) applyCrossSync(key, "ppt");
      if ($(this).hasClass("slide-rich-text-preview")) {
        try { this.focus({ preventScroll: true }); } catch (err) { this.focus(); }
        return;
      }
      enterMathEdit($(this).closest("[data-math-row]"));
    });

    $ctx.on("click.slide", ".slide-item-content, .slide-textbox [data-math-row], .slide-equation-row", function (e) {
      if ($(e.target).is("input, textarea, button, .slide-math-preview")) return;
      e.stopPropagation();
      enterMathEdit($(this).closest("[data-math-row]"));
    });

    $ctx.on("mousedown.slide", ".slide-math-preview", function (e) {
      e.stopPropagation();
    });

    $ctx.on("click.slide", ".slide-title-input, .slide-subtitle-input, .slide-item-input, .slide-eq-input, .slide-notes-input, .slide-textbox-content, .slide-callout-content, .slide-placeholder-label, [data-th], [data-tr], [data-tc]", function (e) {
      e.stopPropagation();
    });

    $ctx.on("select.sync mouseup.sync keyup.sync", "[data-sync-key]", function () {
      if (syncSelectionLock) return;
      if ($(this).hasClass("slide-rich-text-preview")) {
        syncSingleRichText($(this));
        rememberRichTextSelection(this);
      }
      var key = $(this).data("sync-key");
      if (!key) return;
      if (this.selectionStart !== undefined && this.selectionEnd !== undefined && this.selectionStart === this.selectionEnd) {
        if (!$(this).is(":focus")) return;
      }
      applyCrossSync(key, "ppt");
    });

    $ctx.on("focus.slide", "[data-sync-key]", function () {
      if (syncSelectionLock) return;
      var key = $(this).data("sync-key");
      if (key) applyCrossSync(key, "ppt");
    });

    $ctx.on("input.slide change.slide", ".slide-title-input, .slide-subtitle-input, .slide-item-input, .slide-eq-input, .slide-notes-input, .slide-textbox-content, .slide-callout-content, .slide-rich-text-preview, .slide-placeholder-label, [data-th], [data-tr], [data-tc]", function () {
      if ($(this).hasClass("slide-rich-text-preview")) {
        syncSingleRichText($(this));
        rememberRichTextSelection(this);
      }
      updateScopedMathPreviews(mathPreviewScope($(this)));
      saveCurrentSlide();
      scheduleLatexSync();
      scheduleHistoryCommit();
    });

    $ctx.on("blur.slide", ".slide-rich-text-preview", function () {
      var $preview = $(this);
      var $host = mathPreviewScope($preview);
      syncSingleRichText($preview);
      setTimeout(function () {
        updateScopedMathPreviews($host);
      }, 0);
    });

    $ctx.on("click.slide", '[data-action="add-item"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      if (!slide.items) slide.items = [];
      slide.items.push("");
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
      enterMathEdit($("#slideCanvas").find(".slide-item-input").last().closest("[data-math-row]"));
    });

    $ctx.on("click.slide", '[data-action="remove-item"]', function (e) {
      e.stopImmediatePropagation();
      var idx = parseInt($(this).data("item"), 10);
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.items.splice(idx, 1);
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="add-table-row"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.table = normalizeTable(slide.table);
      slide.table.rows.push(slide.table.headers.map(function () { return ""; }));
      renderSlideEditor(slide);
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="add-table-col"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.table = normalizeTable(slide.table);
      slide.table.headers.push("列 " + (slide.table.headers.length + 1));
      $.each(slide.table.rows, function (_i, row) { row.push(""); });
      renderSlideEditor(slide);
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="remove-table-row"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      if (!slide.table) return;
      slide.table = normalizeTable(slide.table);
      if (slide.table.rows.length > 1) slide.table.rows.pop();
      renderSlideEditor(slide);
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="remove-table-col"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      if (!slide.table) return;
      slide.table = normalizeTable(slide.table);
      if (slide.table.headers.length > 1) {
        slide.table.headers.pop();
        $.each(slide.table.rows, function (_i, row) { row.pop(); });
      }
      renderSlideEditor(slide);
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="remove-table"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.table = null;
      renderSlideEditor(slide);
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="add-placeholder"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.placeholders = normalizePlaceholders(slide.placeholders);
      slide.placeholders.push({
        type: "image",
        label: "图片占位",
        position: "right",
        x: 570,
        y: 150,
        width: 245,
        height: 230,
      });
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="remove-placeholder"]', function (e) {
      e.stopImmediatePropagation();
      var idx = parseInt($(this).data("ph"), 10);
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.placeholders = normalizePlaceholders(slide.placeholders);
      slide.placeholders.splice(idx, 1);
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="apply-review-background"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.reviewBackground = true;
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
      setStatus("已应用复习页面背景", "success");
    });

    $ctx.on("click.slide", '[data-action="insert-image"]', function (e) {
      e.stopImmediatePropagation();
      $("#imageUploader").val("").trigger("click");
    });

    $ctx.on("click.slide", '[data-action="remove-image"]', function (e) {
      e.stopImmediatePropagation();
      var idx = parseInt($(this).data("img"), 10);
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.images.splice(idx, 1);
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="add-textbox"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      if (!slide.textboxes) slide.textboxes = [];
      var fontSize = parseInt($("#toolbarFontSize").val(), 10) || 14;
      var color = $("#toolbarFontColor").val() || "#333333";
      slide.textboxes.push({
        text: "",
        color: color,
        bg: "",
        fontSize: fontSize,
        width: 260,
        height: 96,
        x: 56 + slide.textboxes.length * 18,
        y: 190 + slide.textboxes.length * 22,
        align: "left",
        bold: false,
        italic: false,
      });
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
      enterMathEdit($("#slideCanvas").find(".slide-textbox-content").last().closest("[data-math-row]"));
    });

    $ctx.on("click.slide", '[data-action="add-callout"]', function (e) {
      e.stopImmediatePropagation();
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      if (!slide.callouts) slide.callouts = [];
      var idx = slide.callouts.length;
      slide.callouts.push({
        text: "蓝色箭头框",
        x: 130 + idx * 18,
        y: 178 + idx * 18,
        width: 250,
        height: 92,
        fontSize: parseInt($("#toolbarFontSize").val(), 10) || 12,
        align: "center",
      });
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
      $("#slideCanvas").find(".slide-callout-content").last().focus().select();
    });

    $ctx.on("click.slide", '[data-action="remove-textbox"]', function (e) {
      e.stopImmediatePropagation();
      var idx = parseInt($(this).data("tb"), 10);
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.textboxes.splice(idx, 1);
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });

    $ctx.on("click.slide", '[data-action="remove-callout"]', function (e) {
      e.stopImmediatePropagation();
      var idx = parseInt($(this).data("callout"), 10);
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      if (!slide.callouts) slide.callouts = [];
      slide.callouts.splice(idx, 1);
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });
  }

  function bindToolbarEvents($ctx) {
    $ctx.off("input.toolbar change.toolbar mousedown.toolbar click.toolbar");

    $ctx.on("mousedown.toolbar", ".slide-toolbar input, .slide-toolbar select, .slide-toolbar button", function (e) {
      if (this.tagName === "BUTTON") e.preventDefault();
    });

    function afterRichTextFormat() {
      if (!lastFocusedRichText) return;
      syncSingleRichText($(lastFocusedRichText));
      rememberRichTextSelection(lastFocusedRichText);
      saveCurrentSlide();
      scheduleLatexSync();
      scheduleHistoryCommit();
    }

    function formatRichSelection(command, value) {
      if (!lastFocusedRichText || !restoreRichTextSelection()) return false;
      var selection = window.getSelection ? window.getSelection() : null;
      if (!selection || !selection.rangeCount || selection.isCollapsed) return false;
      try {
        document.execCommand(command, false, value);
        afterRichTextFormat();
        return true;
      } catch (err) {
        return false;
      }
    }

    function applyRichSelectionStyle(styles) {
      if (!lastFocusedRichText) return false;
      var selection = window.getSelection ? window.getSelection() : null;
      if (!selection || !selection.rangeCount || selection.isCollapsed) {
        if (!restoreRichTextSelection()) return false;
        selection = window.getSelection ? window.getSelection() : null;
      }
      if (!selection || !selection.rangeCount || selection.isCollapsed) return false;
      var range = selection.getRangeAt(0);
      if (!selectionInsideElement(lastFocusedRichText, range)) return false;
      var span = document.createElement("span");
      Object.keys(styles || {}).forEach(function (key) {
        span.style[key] = styles[key];
      });
      try {
        span.appendChild(range.extractContents());
        range.insertNode(span);
        selection.removeAllRanges();
        var nextRange = document.createRange();
        nextRange.selectNodeContents(span);
        selection.addRange(nextRange);
        afterRichTextFormat();
        return true;
      } catch (err) {
        return false;
      }
    }

    function applyToolbarFontColor(value) {
      if (applyRichSelectionStyle({ color: value })) return;
    }

    $ctx.on("input.toolbar change.toolbar", "#toolbarFontColor", function () {
      applyToolbarFontColor($(this).val() || "#333333");
    });

    $ctx.on("input.toolbar", "#toolbarBgColor", function () {
      if (lastFocusedTextbox) {
        $(lastFocusedTextbox).css("background-color", $(this).val());
        updateScopedMathPreviews($(lastFocusedTextbox));
        saveCurrentSlide();
        scheduleLatexSync();
        scheduleHistoryCommit();
      }
    });

    $ctx.on("click.toolbar", "#toolbarResetBgColor", function (e) {
      e.preventDefault();
      if (lastFocusedTextbox) {
        $(lastFocusedTextbox).css("background-color", "#ffffff");
        updateScopedMathPreviews($(lastFocusedTextbox));
        saveCurrentSlide();
        scheduleLatexSync();
        scheduleHistoryCommit();
      }
      $("#toolbarBgColor").val("#ffffff");
    });

    $ctx.on("change.toolbar", "#toolbarFontSize", function () {
      if (formatRichSelection("fontSize", "7")) {
        $(lastFocusedRichText).find("font[size='7']").each(function () {
          var span = document.createElement("span");
          span.style.fontSize = $("#toolbarFontSize").val() + "px";
          span.innerHTML = this.innerHTML;
          this.replaceWith(span);
        });
        afterRichTextFormat();
        return;
      }
      if (lastFocusedInput) {
        $(lastFocusedInput).css("font-size", $(this).val() + "px");
        updateScopedMathPreviews(mathPreviewScope($(lastFocusedInput)));
        saveCurrentSlide();
        scheduleLatexSync();
        scheduleHistoryCommit();
      }
    });

    $ctx.on("change.toolbar", "#toolbarTextAlign", function () {
      if (lastFocusedRichText) {
        $(lastFocusedRichText).css("text-align", $(this).val());
        syncSingleRichText($(lastFocusedRichText));
        saveCurrentSlide();
        scheduleLatexSync();
        scheduleHistoryCommit();
        return;
      }
      if (lastFocusedInput) {
        $(lastFocusedInput).css("text-align", $(this).val());
        updateScopedMathPreviews(mathPreviewScope($(lastFocusedInput)));
        saveCurrentSlide();
        scheduleLatexSync();
        scheduleHistoryCommit();
      }
    });

    $ctx.on("click.toolbar", '[data-action="toggle-bold"]', function (e) {
      e.stopImmediatePropagation();
      if (formatRichSelection("bold")) return;
      if (lastFocusedInput) {
        var $input = $(lastFocusedInput);
        var isBold = parseInt($input.css("font-weight"), 10) >= 600;
        $input.css("font-weight", isBold ? "400" : "700");
        updateScopedMathPreviews(mathPreviewScope($input));
        saveCurrentSlide();
        scheduleLatexSync();
        scheduleHistoryCommit();
      }
    });

    $ctx.on("click.toolbar", '[data-action="toggle-italic"]', function (e) {
      e.stopImmediatePropagation();
      if (formatRichSelection("italic")) return;
      if (lastFocusedInput) {
        var $input = $(lastFocusedInput);
        var isItalic = $input.css("font-style") === "italic";
        $input.css("font-style", isItalic ? "normal" : "italic");
        updateScopedMathPreviews(mathPreviewScope($input));
        saveCurrentSlide();
        scheduleLatexSync();
        scheduleHistoryCommit();
      }
    });
  }

  $("#imageUploader").on("change", function () {
    var file = this.files[0];
    if (!file) return;

    var formData = new FormData();
    formData.append("file", file);
    setStatus("正在上传图片...", "info");

    $.ajax({
      url: "/beamer-generator/api/upload-image",
      method: "POST",
      data: formData,
      processData: false,
      contentType: false,
      success: function (data) {
        if (data.error) {
          setStatus("图片上传失败: " + data.error, "error");
          return;
        }
        saveCurrentSlide();
        var slide = slidesData.slides[currentSlideIdx];
        slide.images.push({
          path: data.url,
          x: 520,
          y: 150,
          width: 240,
          height: 170,
        });
        renderSlideEditor(slide);
        renderSlideList();
        commitHistorySnapshot(false);
        scheduleLatexSync();
        setStatus("操作完成", "success");
      },
      error: function () {
        setStatus("图片上传失败", "error");
      },
    });

    $(this).val("");
  });

  function saveCurrentSlide() {
    if (!slidesData || currentSlideIdx < 0) return;
    var slide = slidesData.slides[currentSlideIdx];
    var $canvas = $("#slideCanvas");
    if ($canvas.find(".slide-title-input").length === 0) return;

    syncRichTextSources($canvas);

    var titleVal = $canvas.find('[data-field="title"]').val();
    if (titleVal !== undefined) slide.title = titleVal;
    slide.titleRichHtml = $canvas.find(".slide-title-rich").data("rich-html") || "";

    var subVal = $canvas.find('[data-field="subtitle"]').val();
    if (subVal !== undefined) slide.subtitle = subVal;
    slide.subtitleRichHtml = $canvas.find(".slide-subtitle-rich").data("rich-html") || "";

    var items = [];
    var itemRichHtml = [];
    $canvas.find(".slide-item-input").each(function () {
      items.push($(this).val());
      itemRichHtml.push($(this).closest("[data-math-row]").find(".slide-rich-text-preview").data("rich-html") || "");
    });
    if (items.length > 0 || slide.items.length > 0) {
      slide.items = items;
      slide.itemRichHtml = itemRichHtml;
    }

    var eqs = [];
    $canvas.find(".slide-eq-input").each(function () {
      var eq = cleanEquationForPpt($(this).val());
      if (eq) eqs.push(eq);
    });
    slide.equations = eqs;
    normalizeSlideEquations(slide);

    if (slide.table && slide.table.headers) {
      slide.table.headerRichHtml = [];
      $canvas.find("[data-th]").each(function () {
        var j = parseInt($(this).data("th"), 10);
        slide.table.headers[j] = $(this).val();
        slide.table.headerRichHtml[j] = $(this).closest("th").find(".slide-rich-text-preview").data("rich-html") || "";
      });
      slide.table.rowRichHtml = slide.table.rowRichHtml || [];
      $canvas.find("[data-tr]").each(function () {
        var i = parseInt($(this).data("tr"), 10);
        var j = parseInt($(this).data("tc"), 10);
        if (slide.table.rows[i]) slide.table.rows[i][j] = $(this).val();
        if (!slide.table.rowRichHtml[i]) slide.table.rowRichHtml[i] = [];
        slide.table.rowRichHtml[i][j] = $(this).closest("td").find(".slide-rich-text-preview").data("rich-html") || "";
      });
    }

    var notesVal = $canvas.find('[data-field="notes"]').val();
    if (notesVal !== undefined) slide.notes = notesVal;

    var placeholders = [];
    var renderScale = slideScale($canvas.find(".slide-render").first());
    $canvas.find(".slide-image-placeholder").each(function () {
      var $ph = $(this);
      var label = $ph.find(".slide-placeholder-label").val() || "图片占位";
      var figure = extractFigureReference($ph.data("figure") || label);
      placeholders.push({
        type: "image",
        label: label,
        figure: figure,
        asset: $ph.data("asset") || "",
        position: "",
        x: fromSlidePx(parseFloat($ph.css("left")) || 0, renderScale),
        y: fromSlidePx(parseFloat($ph.css("top")) || 0, renderScale),
        width: fromSlidePx(cssPx($ph, "width", 245), renderScale),
        height: fromSlidePx(cssPx($ph, "height", 230), renderScale),
      });
    });
    var previousPlaceholders = normalizePlaceholders(slide.placeholders || []);
    if (!placeholders.length && previousPlaceholders.length) {
      slide.placeholders = previousPlaceholders;
    } else {
      var byFigure = {};
      previousPlaceholders.forEach(function (ph) {
        var key = normalizeFigureLabel(ph.figure || ph.label || "");
        if (key) byFigure[key] = ph;
      });
      placeholders.forEach(function (ph) {
        var key = normalizeFigureLabel(ph.figure || ph.label || "");
        if (key && byFigure[key]) {
          ph.asset = ph.asset || byFigure[key].asset || "";
          ph.figure = ph.figure || byFigure[key].figure || "";
          ph.label = ph.label || byFigure[key].label || "";
        }
      });
      slide.placeholders = placeholders;
    }
    ensureSlideFigurePlaceholders(slide);

    if (!slide.textboxes) slide.textboxes = [];
    var tbs = [];
    $canvas.find(".slide-textbox").each(function () {
      var $tb = $(this);
      var $content = $tb.find(".slide-textbox-content");
      tbs.push({
        text: $content.val(),
        color: $content.css("color") || "#333333",
        bg: $tb.css("background-color") || "",
        fontSize: parseInt($content.css("font-size"), 10) || 14,
        width: cssPx($tb, "width", 260),
        height: cssPx($tb, "height", 96),
        x: parseFloat($tb.css("left")) || 0,
        y: parseFloat($tb.css("top")) || 0,
        align: $content.css("text-align") || "left",
        bold: parseInt($content.css("font-weight"), 10) >= 600,
        italic: $content.css("font-style") === "italic",
        richHtml: $tb.find(".slide-rich-text-preview").data("rich-html") || "",
      });
    });
    slide.textboxes = tbs;

    var callouts = [];
    $canvas.find(".slide-callout").each(function () {
      var $callout = $(this);
      var $content = $callout.find(".slide-callout-content");
      callouts.push({
        text: repairPptLatexArtifacts($content.val()),
        fontSize: parseInt($content.css("font-size"), 10) || 12,
        width: fromSlidePx(cssPx($callout, "width", 250), renderScale),
        height: fromSlidePx(cssPx($callout, "height", 92), renderScale),
        x: fromSlidePx(parseFloat($callout.css("left")) || 0, renderScale),
        y: fromSlidePx(parseFloat($callout.css("top")) || 0, renderScale),
        align: $content.css("text-align") || "center",
      });
    });
    slide.callouts = callouts;

    if (slide.images && slide.images.length) {
      $canvas.find(".slide-image-item").each(function () {
        var idx = parseInt($(this).data("img"), 10);
        if (slide.images[idx]) {
          slide.images[idx].width = fromSlidePx(cssPx($(this), "width", 220), renderScale);
          slide.images[idx].height = fromSlidePx(cssPx($(this), "height", 150), renderScale);
          slide.images[idx].x = fromSlidePx(parseFloat($(this).css("left")) || 0, renderScale);
          slide.images[idx].y = fromSlidePx(parseFloat($(this).css("top")) || 0, renderScale);
        }
      });
    }
  }

  function deleteSlide(idx) {
    if (!slidesData || slidesData.slides.length <= 1) {
      setStatus("至少保留一页幻灯片", "error");
      return;
    }

    saveCurrentSlide();
    slidesData.slides.splice(idx, 1);
    for (var i = 0; i < slidesData.slides.length; i++) {
      slidesData.slides[i].id = i;
    }

    if (currentSlideIdx >= slidesData.slides.length) {
      currentSlideIdx = slidesData.slides.length - 1;
    }

    renderSlideList();
    if (currentSlideIdx >= 0) selectSlide(currentSlideIdx);
    scheduleLatexSync();
    setStatus("操作完成", "success");
  }

  $("#btnAddSlide").on("click", function () {
    if (!slidesData) return;
    saveCurrentSlide();
    var newSlide = {
      id: slidesData.slides.length,
      type: "content",
      title: "新页面",
      subtitle: "",
      items: [""],
      equations: [],
      table: null,
      notes: "",
      images: [],
      placeholders: [],
      textboxes: [],
      callouts: [],
    };
    slidesData.slides.push(newSlide);
    renderSlideList();
    selectSlide(slidesData.slides.length - 1);
    scheduleLatexSync();
    setStatus("操作完成", "success");
  });

  function postProjectBlob(paths, payload) {
    var index = 0;
    function tryNext(lastError) {
      if (index >= paths.length) return Promise.reject(lastError || new Error("请求失败"));
      var url = paths[index++];
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(function (resp) {
        if (!resp.ok) {
          var err = new Error("HTTP " + resp.status);
          if ((resp.status === 404 || resp.status === 405) && index < paths.length) return tryNext(err);
          throw err;
        }
        return resp.blob();
      }).catch(function (err) {
        if (index < paths.length) return tryNext(err);
        throw err;
      });
    }
    return tryNext();
  }

  function postProjectJson(paths, payload) {
    var index = 0;
    function tryNext(lastError) {
      if (index >= paths.length) return Promise.reject(lastError || new Error("请求失败"));
      var url = paths[index++];
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload),
      }).then(function (resp) {
        if (!resp.ok) {
          var err = new Error("HTTP " + resp.status);
          if ((resp.status === 404 || resp.status === 405) && index < paths.length) return tryNext(err);
          throw err;
        }
        return resp.json();
      }).catch(function (err) {
        if (index < paths.length) return tryNext(err);
        throw err;
      });
    }
    return tryNext();
  }

  $("#btnSaveProject").on("click", function () {
    var enteredTitle = ($("#pptChapterTitleInput").val() || "").trim();
    if (!enteredTitle) {
      setStatus("请输入 PPT 保存名称", "error");
      $("#pptChapterTitleInput").focus();
      return;
    }
    var payload = buildProjectSavePayload();
    if (!payload) return;
    var $button = $(this);
    $button.prop("disabled", true).text("保存中...");
    setStatus("正在保存到网页端已保存内容...", "info");

    postProjectJson(["/beamer-generator/api/save-project", "/beamer-generator/api/save-project/", "/api/save-project"], payload)
      .then(function (data) {
        return loadSavedPptProjects().then(function () {
          setStatus("保存完成：已保存到网页端“查找已保存内容”中（" + (data.chapter_title || enteredTitle) + "）", "success");
        });
      })
      .catch(function (err) {
        setStatus("保存失败: " + err.message, "error");
      })
      .finally(function () {
        $button.prop("disabled", false).text("保存");
      });
  });

  $("#btnDownloadPptx").on("click", function () {
    if (!slidesData) return;
    var payload = buildProjectSavePayload();
    if (!payload) return;
    setStatus("正在生成 PPTX 文件...", "info");
    delete payload.latex;

    postProjectBlob(["/beamer-generator/api/export-pptx", "/beamer-generator/api/export-pptx/", "/api/export-pptx"], payload)
      .then(function (blob) {
        downloadFile(blob, "presentation_" + today() + ".pptx",
          "application/vnd.openxmlformats-officedocument.presentationml.presentation");
    setStatus("操作完成", "success");
      })
      .catch(function (err) {
        setStatus("PPTX 生成请求失败: " + err.message, "error");
      });
  });

  $(document).on("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      $("#btnGenerate").click();
    }
  });

  $("#savedLectureSelect, #btnRefreshSavedLectures").hide();
  $("#btnImportMarkdown").text("导入 MD 知识图谱");
  loadSavedPptProjects();
  setupColumnResize();
  collapsedPaneResize = setupCollapsedPaneResize();
  updateContentPreview();
  setActiveTab("latex");
  applyInputCollapsedState();
  setGenerating(false);
  updateDownloadPptxButton();
});

