$(function () {
  "use strict";

  var editor = CodeMirror.fromTextArea(document.getElementById("editor"), {
    mode: "stex",
    theme: "monokai",
    lineNumbers: true,
    lineWrapping: true,
    readOnly: false,
    extraKeys: {
      "Alt-Up": function (cm) { scrollLatexEditorByLine(cm, -1); },
      "Alt-Down": function (cm) { scrollLatexEditorByLine(cm, 1); },
      "Ctrl-Shift-Up": function (cm) { scrollLatexEditorByLine(cm, -1); },
      "Ctrl-Shift-Down": function (cm) { scrollLatexEditorByLine(cm, 1); },
    },
  });

  var isGenerating = false;
  var latexGenerateStatusMessage = "";
  var fullLatex = "";
  var sourceLatex = "";
  var slidesData = null;
  var currentSlideIdx = -1;
  var activeTab = "latex";
  var lastFocusedInput = null;
  var lastFocusedTextbox = null;
  var lastFocusedRichText = null;
  var savedRichTextRange = null;
  var toolbarSelectionHoldUntil = 0;
  var latexSyncTimer = null;
  var currentCustomRequirements = "";
  var generatedOutline = null;
  var activeOutlineSectionIndex = 0;
  var pageChecklistText = "";
  var pageChecklistTimer = null;
  var GPT_CONFIG_STORAGE_KEY = "beamer_generator_gpt_config_v1";
  var OUTLINE_STORAGE_KEY = "beamer_generator_saved_outline_v1";
  var activeGptConfig = null;
  var historyTimer = null;
  var undoStack = [];
  var redoStack = [];
  var historyLock = false;
  var HISTORY_LIMIT = 4;

  function scrollLatexEditorByLine(cm, direction) {
    if (!cm || typeof cm.scrollTo !== "function" || typeof cm.getScrollInfo !== "function") return;
    var info = cm.getScrollInfo();
    var lineHeight = typeof cm.defaultTextHeight === "function" ? cm.defaultTextHeight() : 18;
    var maxTop = Math.max(0, info.height - info.clientHeight);
    var nextTop = Math.max(0, Math.min(maxTop, info.top + direction * lineHeight));
    cm.scrollTo(null, nextTop);
  }

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
  var selectedSavedPptProjectIndex = null;
  var savedPptLoadError = "";
  var savedSlideDragPayload = null;
  var savedPptGalleryManualPosition = null;
  var slideThumbDragIndex = null;
  var inputCollapsed = localStorage.getItem("bg_input_panel_collapsed") === "1";
  var latexSyncMap = {};
  var latexSyncMarks = [];
  var currentSyncKey = "";
  var latexSelectionTimer = null;
  var syncSelectionLock = false;
  var suppressLatexSelectionSyncUntil = 0;
  var suppressPptSelectionSyncUntil = 0;
  var pptSyncHighlightTimer = null;
  var latexProgrammaticUpdate = false;
  var latexManualSyncTimer = null;
  var latexManualSyncSeq = 0;
  var suppressNextLatexManualSync = false;
  var latexGenerateProgress = 0;
  var outlineGenerateProgress = 0;
  var outlineProgressTimer = null;
  var queuedStatusMessage = null;
  var importedPackageImages = [];
  var importedPreviewImages = [];
  var importPreviewPanelOpen = false;
  var importPreviewTitle = "导入内容预览";
  var packageImagePanelOpen = false;
  var editedImageGeometry = { placeholders: {}, images: {} };
  var rawMarkdownContent = "";
  var selectedMarkdownSectionIds = {};
  var importedPackageAssetUrls = {};
  var packageImageViewerOpen = false;
  var figurePreviewMap = {};
  var figureHoverPreviewOpen = false;
  var importedMarkdownFiles = [];
  var activeMarkdownPreviewIndex = null;
  var importedEquationCatalog = [];
  var extraEquationCatalog = [];
  var missingEquationCatalog = [];
  var supplementChapterCatalog = [];
  var latexPptSplitRatio = parseFloat(localStorage.getItem("bg_latex_ppt_split_ratio") || "0.5");
  if (Number.isNaN(latexPptSplitRatio)) latexPptSplitRatio = 0.5;
  latexPptSplitRatio = Math.max(0.25, Math.min(0.75, latexPptSplitRatio));
  var collapsedPaneResize = null;
  var urlParams = new URLSearchParams(window.location.search || "");
  var appMode = urlParams.get("mode") || "generate";
  var isLatexImportMode = appMode === "latex-import";
  var importedLatexFileName = "";
  var importedPdfFileName = "";

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
    var text = String(label || "");
    var m = text.match(/(?:Figure|Fig\.?|图)\s*(\d+(?:[._]\d+)?)/i);
    if (m) return "figure " + String(m[1] || "").replace(/_/g, ".");
    return text.replace(/\s+/g, " ").trim().toLowerCase();
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

  function uniqueList(values) {
    var seen = {};
    var result = [];
    (values || []).forEach(function (value) {
      value = String(value || "").trim();
      if (!value || seen[value]) return;
      seen[value] = true;
      result.push(value);
    });
    return result;
  }

  function pad2(value) {
    var n = parseInt(value, 10);
    if (Number.isNaN(n)) return "";
    return n < 10 ? "0" + n : String(n);
  }

  function figureNumberParts(label) {
    var match = String(label || "").match(/\d+(?:\.\d+)?/);
    if (!match) return null;
    var parts = match[0].split(".");
    return {
      raw: match[0],
      major: parts[0] || "",
      minor: parts.length > 1 ? (parts[1] || "") : "",
    };
  }

  function figureAssetCodes(label) {
    var parts = figureNumberParts(label);
    if (!parts) return [];
    var codes = [];
    var digits = parts.raw.replace(/[^0-9]/g, "");
    if (digits) codes.push(digits);
    if (parts.minor) {
      codes.push(parts.major + parts.minor);
      codes.push(parts.major + pad2(parts.minor));
      codes.push(pad2(parts.major) + parts.minor);
      codes.push(pad2(parts.major) + pad2(parts.minor));
    }
    return uniqueList(codes).sort(function (a, b) { return b.length - a.length; });
  }

  function inferFigureLabelsFromAssetName(name) {
    var rawName = String(name || "").toLowerCase().replace(/\\/g, "/").split("/").pop();
    var stem = normalizeAssetStem(rawName.replace(/\.[a-z0-9]+$/i, ""));
    var labels = [];
    if (!stem) return labels;

    String(rawName).replace(/(?:figure|fig\.?|图)[^0-9]*(\d{1,3})[._-](\d{1,3})/ig, function (_match, major, minor) {
      labels.push("Figure " + parseInt(major, 10) + "." + parseInt(minor, 10));
      return _match;
    });
    String(rawName).replace(/(^|[^0-9])(\d{1,3})[._-](\d{1,3})(?=[^0-9]|$)/g, function (_match, _prefix, major, minor) {
      labels.push("Figure " + parseInt(major, 10) + "." + parseInt(minor, 10));
      return _match;
    });

    var runs = stem.match(/\d+/g) || [];
    runs.forEach(function (run) {
      if (!/(figure|fig|图)/i.test(rawName)) return;
      if (run.length >= 4) {
        var code = run.slice(-4);
        labels.push("Figure " + parseInt(code.slice(0, 2), 10) + "." + parseInt(code.slice(2), 10));
      } else if (run.length === 3) {
        labels.push("Figure " + parseInt(run.slice(0, 1), 10) + "." + parseInt(run.slice(1), 10));
        labels.push("Figure " + parseInt(run.slice(0, 2), 10) + "." + parseInt(run.slice(2), 10));
      } else if (run.length === 2) {
        labels.push("Figure " + parseInt(run.slice(0, 1), 10) + "." + parseInt(run.slice(1), 10));
      }
    });

    return uniqueList(labels.filter(function (label) {
      return !/NaN/.test(label);
    }));
  }

  function pickPackageImageForFigure(label) {
    var labelKey = normalizeFigureLabel(label);
    var digits = labelKey.replace(/[^0-9]/g, "");
    var dotted = (labelKey.match(/\d+(?:\.\d+)?/) || [""])[0];
    var dashed = dotted.replace(/\./g, "-");
    var underscored = dotted.replace(/\./g, "_");
    var compact = normalizeAssetStem(labelKey);
    var assetCodes = figureAssetCodes(label);
    var best = "";

    for (var i = 0; i < importedPackageImages.length; i++) {
      var img = importedPackageImages[i];
      var rawName = String((img && img.name) || "").toLowerCase();
      var stem = normalizeAssetStem(rawName);
      if (!stem) continue;
      var figureNamedFile = rawName.indexOf("figure") !== -1 || rawName.indexOf("fig") !== -1;
      if (dotted && rawName === dotted + rawName.slice(rawName.lastIndexOf("."))) return img.url;
      if (dotted && rawName.indexOf(dotted) !== -1) return img.url;
      if (dashed && rawName.indexOf(dashed) !== -1) return img.url;
      if (underscored && rawName.indexOf(underscored) !== -1) return img.url;
      if (figureNamedFile && dotted && rawName.indexOf(dotted) !== -1) return img.url;
      if (figureNamedFile && dashed && rawName.indexOf(dashed) !== -1) return img.url;
      if (figureNamedFile && underscored && rawName.indexOf(underscored) !== -1) return img.url;
      for (var c = 0; c < assetCodes.length; c++) {
        if (figureNamedFile && assetCodes[c] && stem.indexOf(assetCodes[c]) !== -1) return img.url;
      }
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
      var inferredLabels = inferFigureLabelsFromAssetName(match[2]);
      var label = labelMatch ? extractFigureReference(labelMatch[0]) : (findNearbyFigureLabel(lines, i) || inferredLabels[0] || "");
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
      inferredLabels.forEach(function (assetLabel) {
        var key = normalizeFigureLabel(assetLabel);
        if (!key || figurePreviewMap[key]) return;
        figurePreviewMap[key] = {
          label: assetLabel,
          url: url,
          assetUrl: match[2],
          caption: caption || assetLabel,
        };
      });
    }

    importedPackageImages.forEach(function (img) {
      inferFigureLabelsFromAssetName(img && img.name).forEach(function (label) {
        var key = normalizeFigureLabel(label);
        if (!key || figurePreviewMap[key]) return;
        figurePreviewMap[key] = {
          label: label,
          url: img.url,
          assetUrl: img.name,
          caption: img.name || label,
        };
      });
    });

    var orderedRefs = collectFigureReferences(source);
    var imageCursor = 0;
    orderedRefs.forEach(function (ref) {
      var key = normalizeFigureLabel(ref);
      if (!key || figurePreviewMap[key]) return;
      var explicitUrl = pickPackageImageForFigure(ref);
      var img = null;
      if (explicitUrl) {
        img = { url: explicitUrl, name: ref };
      } else {
        while (imageCursor < importedPackageImages.length) {
          img = importedPackageImages[imageCursor++];
          if (img && img.url) break;
          img = null;
        }
      }
      if (!img || !img.url) return;
      figurePreviewMap[key] = {
        label: ref,
        url: img.url,
        assetUrl: img.name || "",
        caption: img.name || ref,
      };
    });
  }

  function resolveSlideImageUrl(rawPath) {
    var raw = String(rawPath || "").trim();
    if (!raw) return "";
    if (/^(https?:\/\/|data:|\/beamer-generator\/uploads\/|\/uploads\/)/i.test(raw)) return raw;
    var packageUrl = resolvePackageAssetUrl(raw);
    if (packageUrl) return packageUrl;
    var labels = inferFigureLabelsFromAssetName(raw);
    for (var i = 0; i < labels.length; i++) {
      var figure = figurePreviewMap[normalizeFigureLabel(labels[i])];
      if (figure && figure.url) return figure.url;
      var picked = pickPackageImageForFigure(labels[i]);
      if (picked) return picked;
    }
    return raw;
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
    String(fullLatex || "").replace(/\\(?:includegraphics|safecontentimage|safeverticalimage)(?:\[[^\]]*\])?\{([^{}]+\.(?:png|jpe?g|pdf|webp))\}/gi, function (_match, rawPath) {
      var target = String(rawPath || "").trim().replace(/\\/g, "/");
      if (!target || payload[target]) return _match;
      var url = /^(?:https?:\/\/|data:|\/beamer-generator\/uploads\/|\/uploads\/)/i.test(target)
        ? target
        : resolvePackageAssetUrl(target);
      if (url) payload[target] = url;
      return _match;
    });
    return payload;
  }

  function latexHasExternalGraphicRefs(tex) {
    return /\\(?:includegraphics|safecontentimage|safeverticalimage)(?:\[[^\]]*\])?\{(?!data:)([^{}]+\.(?:png|jpe?g|pdf|webp))\}/i.test(String(tex || ""));
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

  function latexMathDisplaySource(formula) {
    var s = repairPptLatexArtifacts(String(formula || "")).trim();
    if (!s) return "";
    s = s.replace(/^\\\[\s*/, "").replace(/\s*\\\]$/, "");
    s = s.replace(/^\$\$\s*/, "").replace(/\s*\$\$$/, "");
    s = s.replace(/^\\\(\s*/, "").replace(/\s*\\\)$/, "");
    s = s.replace(/^\$\s*/, "").replace(/\s*\$$/, "");
    return s.trim();
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

  function containNestedWheelScroll(event) {
    var target = event.target;
    var scrollNode = $(target).closest(
      ".slide-canvas, .slide-list, .panel, .CodeMirror-scroll, .math-preview, .saved-ppt-slide-gallery, .saved-ppt-chapter-list"
    )[0];
    if (!scrollNode) return;
    var deltaY = event.deltaY || 0;
    if (!deltaY) return;
    var maxScrollTop = scrollNode.scrollHeight - scrollNode.clientHeight;
    if (maxScrollTop <= 0) return;
    var atTop = scrollNode.scrollTop <= 0;
    var atBottom = scrollNode.scrollTop >= maxScrollTop - 1;
    if ((deltaY < 0 && atTop) || (deltaY > 0 && atBottom)) {
      event.preventDefault();
      event.stopPropagation();
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

  function extractEquationCatalog(sourceText, fileName) {
    var source = String(sourceText || "").replace(/\r\n/g, "\n");
    var catalog = [];
    var seen = {};

    function surroundingTitle(index) {
      var lines = source.slice(0, index).split("\n").reverse();
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (/^#{1,6}\s+/.test(line)) return line.replace(/^#{1,6}\s+/, "").trim();
        if (/^\\(?:section|subsection|subsubsection)\*?\{/.test(line)) {
          return line.replace(/^\\(?:section|subsection|subsubsection)\*?\{/, "").replace(/\}\s*$/, "").trim();
        }
      }
      return fileName || "公式章节";
    }

    function nearbyEquationNumber(index) {
      var before = source.slice(Math.max(0, index - 260), index);
      var after = source.slice(index, Math.min(source.length, index + 120));
      var candidates = [before, after];
      for (var i = 0; i < candidates.length; i++) {
        var m = candidates[i].match(/(?:Equation|Eq\.?|公式)\s*[:：]?\s*\(?([0-9]+(?:\.[0-9]+)+)\)?|\(([0-9]+(?:\.[0-9]+)+)\)/i);
        if (m) return m[1] || m[2] || "";
      }
      return "";
    }

    function addEquation(raw, startIndex, envName) {
      var block = repairPptLatexArtifacts(String(raw || "")).trim();
      if (!block) return;
      var number = "";
      block = block.replace(/\\tag\{([^}]*)\}/g, function (_match, value) {
        if (!number) number = String(value || "").trim();
        return "";
      });
      var label = "";
      block = block.replace(/\\label\{([^}]*)\}/g, function (_match, value) {
        if (!label) label = String(value || "").trim();
        return "";
      });
      if (!number) number = nearbyEquationNumber(startIndex || 0);
      var formula = latexMathDisplaySource(block);
      if (!formula || formula.length < 2) return;
      var key = (number || label || formula).replace(/\s+/g, "");
      if (seen[key]) return;
      seen[key] = true;
      catalog.push({
        id: "eq-" + catalog.length,
        number: number || (label ? label.replace(/^eq[:_.-]?/i, "") : String(catalog.length + 1)),
        label: label,
        formula: formula,
        env: envName || "",
        section: surroundingTitle(startIndex || 0),
      });
    }

    var envPattern = /\\begin\{(equation|align|alignat|gather|multline)\*?\}([\s\S]*?)\\end\{\1\*?\}/g;
    var match;
    while ((match = envPattern.exec(source)) !== null) {
      addEquation(match[2], match.index, match[1]);
    }
    var displayPattern = /\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$/g;
    while ((match = displayPattern.exec(source)) !== null) {
      addEquation(match[1] || match[2] || "", match.index, "display");
    }
    if (!catalog.length) {
      var inlinePattern = /(^|[^\\])\$([^$\n]{3,260})\$/g;
      while ((match = inlinePattern.exec(source)) !== null) {
        addEquation(match[2] || "", match.index, "inline");
      }
    }
    return catalog;
  }

  function equationCatalogKey(eq) {
    eq = eq || {};
    if (eq.label) return "label:" + String(eq.label).trim();
    if (eq.number) return "num:" + String(eq.number).trim();
    return "formula:" + latexMathDisplaySource(eq.formula || "").replace(/\s+/g, "");
  }

  function collectCurrentMissingEquations() {
    var items = [];
    var seen = {};

    function add(keyValue, labelValue, context) {
      var key = String(keyValue || "").trim();
      var label = String(labelValue || key || "").trim();
      var raw = label || key;
      if (!raw) return;
      var numberMatch = raw.match(/\d+(?:\.\d+)+|\d+/) || key.match(/\d+(?:\.\d+)+|\d+/);
      var number = numberMatch ? numberMatch[0] : "";
      var dedupeKey = number ? "num:" + number : "label:" + raw.replace(/\s+/g, "");
      if (seen[dedupeKey]) return;
      seen[dedupeKey] = true;
      items.push({
        key: key || raw,
        label: label || key || raw,
        number: number,
        chapterHint: number && number.indexOf(".") > -1 ? ("建议导入第 " + number.split(".")[0] + " 章相关公式章节") : "",
        context: context || "",
      });
    }

    if (slidesData && Array.isArray(slidesData.missing_equations)) {
      slidesData.missing_equations.forEach(function (eq) {
        add((eq && eq.key) || "", (eq && eq.label) || "", "全局缺失公式");
      });
    }
    if (slidesData && Array.isArray(slidesData.slides)) {
      slidesData.slides.forEach(function (slide, idx) {
        (slide.missing_equations || []).forEach(function (eq) {
          var title = slide && slide.title ? String(slide.title) : ("第 " + (idx + 1) + " 页");
          add((eq && eq.key) || "", (eq && eq.label) || "", title);
        });
      });
    }
    var source = "";
    if (editor && editor.getValue) source = editor.getValue();
    else source = fullLatex || "";
    var markerPattern = /\\kgmissingequation\{([^{}]+)\}\{([^{}]*)\}/g;
    var match;
    while ((match = markerPattern.exec(source || "")) !== null) {
      add(match[1], match[2] || match[1], "LaTeX 标记");
    }
    return items;
  }

  function refreshMissingEquationCatalog() {
    missingEquationCatalog = collectCurrentMissingEquations();
    return missingEquationCatalog;
  }

  function currentMissingEquationKeys() {
    var keys = {};

    function add(value) {
      var raw = String(value || "").trim();
      if (!raw) return;
      keys[raw] = true;
      var number = raw.match(/\d+(?:\.\d+)+|\d+/);
      if (number) keys["num:" + number[0]] = true;
      keys["label:" + raw] = true;
    }

    refreshMissingEquationCatalog().forEach(function (eq) {
      add(eq.key);
      add(eq.label);
      if (eq.number) add(eq.number);
    });
    return keys;
  }

  function splitEquationCatalogForCurrentChapter(catalog) {
    var missingKeys = currentMissingEquationKeys();
    var hasMissing = Object.keys(missingKeys).length > 0;
    var matched = [];
    var extra = [];
    (catalog || []).forEach(function (eq) {
      var numberKey = eq && eq.number ? "num:" + String(eq.number).trim() : "";
      var labelKey = eq && eq.label ? "label:" + String(eq.label).trim() : "";
      var isCurrent = !hasMissing || (numberKey && missingKeys[numberKey]) || (labelKey && missingKeys[labelKey]);
      (isCurrent ? matched : extra).push(eq);
    });
    return { matched: matched, extra: extra };
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

  function rememberCurrentRichTextSelection() {
    var selection = window.getSelection ? window.getSelection() : null;
    if (!selection || !selection.rangeCount) return false;
    var range = selection.getRangeAt(0);
    var $root = $(range.commonAncestorContainer.nodeType === 1
      ? range.commonAncestorContainer
      : range.commonAncestorContainer.parentNode);
    var $rich = $root.closest(".slide-rich-text-preview");
    if (!$rich.length && lastFocusedRichText && selectionInsideElement(lastFocusedRichText, range)) {
      $rich = $(lastFocusedRichText);
    }
    if (!$rich.length) return false;
    lastFocusedRichText = $rich[0];
    lastFocusedInput = $rich[0];
    lastFocusedTextbox = $rich.closest(".slide-textbox, .slide-callout")[0] || null;
    savedRichTextRange = range.cloneRange();
    syncToolbarFontSizeFromSelection(range);
    return true;
  }

  function getSelectionFontSizeValue(range) {
    var candidate = null;
    if (!range) return candidate;
    var node = range.commonAncestorContainer;
    if (!node) return candidate;
    if (node.nodeType !== 1) node = node.parentNode;
    if (!node) return candidate;
    var $node = $(node).closest(".slide-rich-text-preview");
    if (!$node.length) return candidate;

    var anchor = range.startContainer;
    if (anchor && anchor.nodeType !== 1) anchor = anchor.parentNode;
    if (!anchor || !document.body.contains(anchor)) return candidate;

    var $target = $(anchor).closest("font, span, strong, b, em, i, u, sub, sup, [style]");
    var el = $target.length ? $target[0] : anchor;
    var computed = window.getComputedStyle ? window.getComputedStyle(el) : null;
    if (!computed || !computed.fontSize) return candidate;
    var size = parseFloat(computed.fontSize);
    if (!size || Number.isNaN(size)) return candidate;
    return Math.round(size);
  }

  function syncToolbarFontSizeFromSelection(range) {
    var value = getSelectionFontSizeValue(range || (window.getSelection && window.getSelection().rangeCount ? window.getSelection().getRangeAt(0) : null));
    if (!value) return;
    var $fontSize = $("#toolbarFontSize");
    if (!$fontSize.length) return;
    $fontSize.val(String(value));
  }

  var richTextSelectionSyncTimer = null;
  function scheduleRichTextSelectionSync() {
    if (richTextSelectionSyncTimer) clearTimeout(richTextSelectionSyncTimer);
    richTextSelectionSyncTimer = setTimeout(function () {
      richTextSelectionSyncTimer = null;
      if (Date.now() < toolbarSelectionHoldUntil) return;
      syncToolbarFontSizeFromSelection();
    }, 0);
  }

  document.addEventListener("selectionchange", function () {
    var active = document.activeElement;
    if (!active) return;
    if (!$(active).closest(".slide-rich-text-preview").length && !$(active).is(".slide-rich-text-preview")) return;
    scheduleRichTextSelectionSync();
  });

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

  function renderMarkdownPreview($target, text, options) {
    var source = repairPptLatexArtifacts(text);
    var opts = options || {};
    $target.empty();
    $target.toggleClass("muted", !source.trim());
    if (!source.trim()) {
      $target.text(opts.emptyText || "暂无内容。");
      return;
    }

    var blocks = source.replace(/\r\n/g, "\n").split(/\n{2,}/);
    blocks.forEach(function (block) {
      var raw = String(block || "");
      if (!raw.trim()) return;
      var lines = raw.split("\n");
      var first = String(lines[0] || "").trim();
      var heading = first.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        var level = Math.min(6, heading[1].length);
        var $heading = $("<h" + level + ' class="markdown-preview-heading"></h' + level + ">");
        renderMathText($heading, heading[2], { displayMode: false, boxedMath: true });
        $target.append($heading);
        if (lines.length > 1) {
          renderMarkdownPreview($target, lines.slice(1).join("\n"), { emptyText: "" });
        }
        return;
      }

      var imageMatch = first.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
      if (imageMatch) {
        var $figure = $('<figure class="markdown-preview-figure"></figure>');
        var $img = $('<img class="markdown-preview-image" />')
          .attr("src", imageMatch[2])
          .attr("alt", imageMatch[1] || "image");
        $figure.append($img);
        if (imageMatch[1]) {
          var $caption = $('<figcaption class="markdown-preview-caption"></figcaption>');
          renderMathText($caption, imageMatch[1], { displayMode: false, boxedMath: true });
          $figure.append($caption);
        }
        $target.append($figure);
        return;
      }

      var isList = lines.every(function (line) {
        return !String(line || "").trim() || /^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(line);
      });
      if (isList) {
        var ordered = lines.some(function (line) { return /^\s*\d+[.)]\s+/.test(line); });
        var $list = $(ordered ? '<ol class="markdown-preview-list"></ol>' : '<ul class="markdown-preview-list"></ul>');
        lines.forEach(function (line) {
          var text = String(line || "").replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+)/, "").trim();
          if (!text) return;
          var $li = $("<li></li>");
          renderMathText($li, text, { displayMode: false, boxedMath: true });
          $list.append($li);
        });
        $target.append($list);
        return;
      }

      var $para = $('<div class="markdown-preview-paragraph"></div>');
      renderMathText($para, raw, { displayMode: false, boxedMath: true });
      $target.append($para);
    });
  }

  function activeMarkdownPreviewSource() {
    if (activeMarkdownPreviewIndex !== null) {
      var item = importedMarkdownFiles[activeMarkdownPreviewIndex];
      if (item && item.content && !item.error) {
        var title = item.path || item.name || ("知识图谱 " + (activeMarkdownPreviewIndex + 1));
        return "# " + title + "\n\n" + item.content;
      }
    }
    return $("#content").val() || "";
  }

  function setMarkdownPreviewSource(text) {
    renderMarkdownPreview($("#contentPreview"), text, {
      emptyText: "导入 .md/.markdown 知识图谱文件后，内容会显示在这里。",
    });
  }

  function updateContentPreview() {
    setMarkdownPreviewSource(activeMarkdownPreviewSource());
  }

  function markdownFileDisplayPath(file) {
    return (file && (file.webkitRelativePath || file.name)) || "未命名 Markdown";
  }

  function markdownSectionId(fileIndex, sectionIndex) {
    return "md-section-" + fileIndex + "-" + sectionIndex;
  }

  function isTextbookSectionHeading(title) {
    return /^chapter\d+_\d+\s*[·.-]/i.test(String(title || "").trim());
  }

  function normalizeMarkdownSectionTitle(rawTitle, fallback) {
    var title = String(rawTitle || "").trim() || fallback || "未命名小节";
    var textbook = title.match(/^(chapter\d+_\d+)\s*[·.-]\s*(.+)$/i);
    if (textbook) {
      var block = textbook[1];
      var rest = textbook[2].trim();
      return block + " · " + rest;
    }
    return title;
  }

  function parseMarkdownSections(content, fileTitle) {
    var source = String(content || "").replace(/\r\n/g, "\n");
    var lines = source.split("\n");
    var headings = [];
    for (var i = 0; i < lines.length; i++) {
      var match = /^(#{1,6})\s+(.+?)\s*$/.exec(lines[i] || "");
      if (!match) continue;
      var level = match[1].length;
      var title = match[2].replace(/\s+#+\s*$/, "").trim();
      headings.push({
        level: level,
        title: title,
        line: i,
        textbook: isTextbookSectionHeading(title),
      });
    }

    var candidates = headings.filter(function (heading) {
      return heading.textbook;
    });
    if (!candidates.length) {
      var lowestUsefulLevel = null;
      headings.forEach(function (heading) {
        if (heading.level <= 1) return;
        lowestUsefulLevel = lowestUsefulLevel === null ? heading.level : Math.min(lowestUsefulLevel, heading.level);
      });
      if (lowestUsefulLevel !== null) {
        candidates = headings.filter(function (heading) {
          return heading.level === lowestUsefulLevel;
        });
      }
    }

    if (!candidates.length && source.trim()) {
      return [{
        title: fileTitle || "全文",
        level: 1,
        startLine: 1,
        endLine: lines.length,
        content: source.trim(),
        expanded: false,
      }];
    }

    return candidates.map(function (heading, index) {
      var endLine = lines.length;
      for (var j = heading.line + 1; j < lines.length; j++) {
        var next = /^(#{1,6})\s+(.+?)\s*$/.exec(lines[j] || "");
        if (next && next[1].length <= heading.level) {
          endLine = j;
          break;
        }
      }
      var sectionContent = lines.slice(heading.line, endLine).join("\n").trim();
      return {
        title: normalizeMarkdownSectionTitle(heading.title, "小节 " + (index + 1)),
        level: heading.level,
        startLine: heading.line + 1,
        endLine: endLine,
        content: sectionContent,
        expanded: false,
      };
    });
  }

  function normalizeSupplementChapterTitle(number, rawTitle) {
    var title = String(rawTitle || "").replace(/\s+#+\s*$/, "").trim();
    return number + (title ? " " + title : "");
  }

  function findSupplementChapterHeadings(lines) {
    var headings = [];
    for (var i = 0; i < lines.length; i++) {
      var line = String(lines[i] || "").trim();
      if (!line) continue;
      var match = /^(?:#{1,6}\s*)?((?:\d{3})(?:\.\d{3})*)\s*(?:[\.、:：\-]\s*)?(.+?)?\s*$/.exec(line);
      if (!match) continue;
      headings.push({
        number: match[1],
        title: normalizeSupplementChapterTitle(match[1], match[2] || ""),
        line: i,
      });
    }
    return headings;
  }

  function extractSupplementChapterCatalog(sourceText, fileName) {
    var source = String(sourceText || "").replace(/\r\n/g, "\n");
    var lines = source.split("\n");
    var headings = findSupplementChapterHeadings(lines);
    var sections = [];
    if (headings.length) {
      sections = headings.map(function (heading, index) {
        var endLine = index + 1 < headings.length ? headings[index + 1].line : lines.length;
        var content = lines.slice(heading.line, endLine).join("\n").trim();
        return {
          id: "supplement-section-" + index,
          number: heading.number,
          title: heading.title || ("补充章节 " + heading.number),
          fileName: fileName || "补充章节",
          startLine: heading.line + 1,
          endLine: endLine,
          content: content,
        };
      });
    } else {
      sections = parseMarkdownSections(source, fileName || "补充章节").map(function (section, index) {
        return {
          id: "supplement-fallback-" + index,
          number: String(index + 1).padStart(3, "0"),
          title: section.title || ("补充章节 " + (index + 1)),
          fileName: fileName || "补充章节",
          startLine: section.startLine || 1,
          endLine: section.endLine || lines.length,
          content: section.content || "",
        };
      });
    }
    return sections.filter(function (section) {
      return String(section.content || "").trim();
    });
  }

  function getSelectedMarkdownSections() {
    var selected = [];
    importedMarkdownFiles.forEach(function (item, fileIndex) {
      if (!item || !item.content || item.error) return;
      (item.sections || []).forEach(function (section, sectionIndex) {
        var id = section.id || markdownSectionId(fileIndex, sectionIndex);
        if (!selectedMarkdownSectionIds[id]) return;
        selected.push({
          id: id,
          fileIndex: fileIndex,
          sectionIndex: sectionIndex,
          fileTitle: item.path || item.name || ("知识图谱 " + (fileIndex + 1)),
          title: section.title || ("小节 " + (sectionIndex + 1)),
          content: section.content || "",
        });
      });
    });
    return selected;
  }

  function renderMarkdownSelectionSummary() {
    var $summary = $("#markdownSelectionSummary");
    if (!$summary.length) return;
    var selected = getSelectedMarkdownSections();
    if (!selected.length) {
      $summary
        .removeClass("has-selection")
        .text(validImportedMarkdownItems().length ? "未引用小节时，生成会使用全部已导入 Markdown 内容。" : "");
      return;
    }
    var labels = selected.slice(0, 3).map(function (section) {
      return section.title;
    }).join("；");
    if (selected.length > 3) labels += " 等";
    $summary
      .addClass("has-selection")
      .text("已引用 " + selected.length + " 个小节：" + labels + "。生成 LaTeX 时只使用这些小节。");
  }

  function renderMarkdownImportList() {
    var $list = $("#markdownImportList");
    if (!$list.length) return;
    $list.empty();
    if (!importedMarkdownFiles.length) {
      $list.removeClass("has-files");
      return;
    }
    $list.addClass("has-files");
    $list.append('<div class="markdown-import-list-title">已导入知识图谱文件</div>');
    importedMarkdownFiles.forEach(function (item, index) {
      if (item && item.sections) {
        item.sections.forEach(function (section, sectionIndex) {
          section.id = section.id || markdownSectionId(index, sectionIndex);
        });
      }
      var meta = item.error
        ? ("导入失败：" + item.error)
        : ((item.charCount || 0) + " 字符" + ((item.sections || []).length ? " · " + item.sections.length + " 个小节" : ""));
      var canExpand = !!(item.content && !item.error);
      var expanded = !!item.expanded && canExpand;
      var sectionHtml = "";
      if (expanded && (item.sections || []).length) {
        sectionHtml += '<div class="markdown-section-tree">';
        (item.sections || []).forEach(function (section, sectionIndex) {
          var id = section.id || markdownSectionId(index, sectionIndex);
          var selected = !!selectedMarkdownSectionIds[id];
          var sectionExpanded = !!section.expanded;
          var lineMeta = "L" + (section.startLine || "?") + "-L" + (section.endLine || "?");
          sectionHtml +=
            '<div class="markdown-section-item' + (selected ? " selected" : "") + '">' +
              '<div class="markdown-section-row">' +
                '<button type="button" class="markdown-section-toggle" data-markdown-index="' + index + '" data-section-index="' + sectionIndex + '" aria-expanded="' + (sectionExpanded ? "true" : "false") + '">' +
                  (sectionExpanded ? "收起" : "展开") +
                '</button>' +
                '<button type="button" class="markdown-section-title" data-markdown-index="' + index + '" data-section-index="' + sectionIndex + '" title="' + escAttr(section.title || "") + '">' +
                  escHtml(section.title || ("小节 " + (sectionIndex + 1))) +
                '</button>' +
                '<div class="markdown-section-meta">' + escHtml(lineMeta) + '</div>' +
                '<button type="button" class="markdown-section-quote' + (selected ? " active" : "") + '" data-markdown-index="' + index + '" data-section-index="' + sectionIndex + '">' +
                  (selected ? "已引用" : "引用") +
                '</button>' +
              '</div>' +
              (sectionExpanded
                ? '<div class="markdown-section-preview">已在下方 Markdown 预览中显示该小节内容。</div>'
                : '') +
            '</div>';
        });
        sectionHtml += '</div>';
      }
      $list.append(
        '<div class="markdown-import-file' + (item.error ? " error" : "") + (activeMarkdownPreviewIndex === index ? " active" : "") + '">' +
          '<div class="markdown-import-file-row">' +
            '<button type="button" class="markdown-import-toggle" data-markdown-index="' + index + '" ' +
              (canExpand ? "" : "disabled ") +
              'aria-expanded="' + (expanded ? "true" : "false") + '">' +
              (expanded ? "收起" : "展开") +
            '</button>' +
            '<div class="markdown-import-path" title="' + escAttr(item.path || item.name || "") + '">' +
              escHtml(item.path || item.name || "") +
            '</div>' +
            '<div class="markdown-import-meta">' + escHtml(meta) + '</div>' +
            '<button type="button" class="markdown-import-remove" data-markdown-index="' + index + '" title="删除该 MD 文件" aria-label="删除 ' + escAttr(item.path || item.name || "MD 文件") + '">&times;</button>' +
          '</div>' +
          (expanded
            ? '<div class="markdown-import-content">点击小节标题可预览，点击“引用”则只用该小节生成 LaTeX。</div>' + sectionHtml
            : '') +
        '</div>'
      );
    });
    renderMarkdownSelectionSummary();
  }

  function toggleMarkdownImportItem(index) {
    if (Number.isNaN(index) || !importedMarkdownFiles[index] || importedMarkdownFiles[index].error) return;
    var nextExpanded = !importedMarkdownFiles[index].expanded;
    importedMarkdownFiles.forEach(function (item, i) {
      item.expanded = i === index ? nextExpanded : false;
    });
    activeMarkdownPreviewIndex = nextExpanded ? index : null;
    renderMarkdownImportList();
    updateContentPreview();
  }

  function previewMarkdownSection(fileIndex, sectionIndex) {
    var item = importedMarkdownFiles[fileIndex];
    if (!item || item.error) return;
    var section = (item.sections || [])[sectionIndex];
    if (!section) return;
    importedMarkdownFiles.forEach(function (fileItem, i) {
      (fileItem.sections || []).forEach(function (candidate, j) {
        candidate.expanded = i === fileIndex && j === sectionIndex ? !candidate.expanded : false;
      });
    });
    activeMarkdownPreviewIndex = null;
    renderMarkdownImportList();
    var fileTitle = item.path || item.name || ("知识图谱 " + (fileIndex + 1));
    setMarkdownPreviewSource("# " + fileTitle + "\n\n" + (section.content || ""));
  }

  function toggleMarkdownSectionSelection(fileIndex, sectionIndex) {
    var item = importedMarkdownFiles[fileIndex];
    if (!item || item.error) return;
    var section = (item.sections || [])[sectionIndex];
    if (!section) return;
    section.id = section.id || markdownSectionId(fileIndex, sectionIndex);
    if (selectedMarkdownSectionIds[section.id]) {
      delete selectedMarkdownSectionIds[section.id];
    } else {
      selectedMarkdownSectionIds[section.id] = true;
    }
    activeMarkdownPreviewIndex = null;
    renderMarkdownImportList();
    refreshMergedMarkdownContent();
  }

  function removeMarkdownImportItem(index) {
    if (Number.isNaN(index) || !importedMarkdownFiles[index]) return;
    var removed = importedMarkdownFiles[index];
    (removed.sections || []).forEach(function (section, sectionIndex) {
      var id = section.id || markdownSectionId(index, sectionIndex);
      delete selectedMarkdownSectionIds[id];
    });
    importedMarkdownFiles.splice(index, 1);
    selectedMarkdownSectionIds = {};
    if (activeMarkdownPreviewIndex === index) {
      activeMarkdownPreviewIndex = null;
    } else if (activeMarkdownPreviewIndex !== null && activeMarkdownPreviewIndex > index) {
      activeMarkdownPreviewIndex -= 1;
    }
    renderMarkdownImportList();
    refreshMergedMarkdownContent();
    var remaining = validImportedMarkdownItems().length;
    setStatus("已删除导入文件：" + (removed.path || removed.name || "MD 文件") + "，剩余 " + remaining + " 个", "success");
  }

  function importMarkdownFile(file) {
    var formData = new FormData();
    formData.append("file", file);
    return $.ajax({
      url: "/beamer-generator/api/import-markdown-source",
      method: "POST",
      data: formData,
      processData: false,
      contentType: false,
    }).then(function (data) {
      if (data && data.error) throw new Error(data.error);
      var content = (data && data.content) || "";
      return {
        name: (data && data.filename) || file.name || "知识图谱",
        path: markdownFileDisplayPath(file),
        content: content,
        charCount: (data && data.char_count) || content.length,
        sections: parseMarkdownSections(content, markdownFileDisplayPath(file)),
      };
    });
  }

  function mergeMarkdownImportContents(items) {
    var selected = getSelectedMarkdownSections();
    if (selected.length) {
      return selected.map(function (section) {
        return [
          "# 引用小节：" + section.fileTitle + " / " + section.title,
          "",
          section.content || ""
        ].join("\n");
      }).join("\n\n---\n\n");
    }
    return items.map(function (item, index) {
      var title = item.path || item.name || ("知识图谱 " + (index + 1));
      return [
        "# 导入知识图谱：" + title,
        "",
        item.content || ""
      ].join("\n");
    }).join("\n\n---\n\n");
  }

  function validImportedMarkdownItems() {
    return importedMarkdownFiles.filter(function (item) {
      return item && item.content && !item.error;
    });
  }

  function refreshMergedMarkdownContent() {
    var imported = validImportedMarkdownItems();
    rawMarkdownContent = imported.length ? mergeMarkdownImportContents(imported) : "";
    applyMarkdownAssets();
    renderMarkdownSelectionSummary();
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
      $("#content").val("");
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

  function renderedPagesToPreviewImages(renderedPages, prefix) {
    return (Array.isArray(renderedPages) ? renderedPages : []).map(function (page, idx) {
      return {
        url: page.image || "",
        name: (prefix || "页面") + " " + (idx + 1),
      };
    }).filter(function (item) {
      return !!item.url;
    });
  }

  function figureAssetsToPreviewImages(figureAssets) {
    return (Array.isArray(figureAssets) ? figureAssets : []).map(function (item, idx) {
      return {
        url: item.url || "",
        name: (item.label || ("Figure " + (idx + 1))) + (item.path ? " · " + item.path : ""),
      };
    }).filter(function (item) {
      return !!item.url;
    });
  }

  function setImportedPreviewImages(items, title) {
    importedPreviewImages = (Array.isArray(items) ? items : []).filter(function (item) {
      return item && item.url;
    });
    importPreviewTitle = title || "导入内容预览";
    if (!importedPreviewImages.length) {
      importPreviewPanelOpen = false;
    }
    renderImportPreviewPanel();
  }

  function renderImportPreviewPanel() {
    var $panel = $("#importPreviewPanel");
    var $grid = $("#importPreviewGrid").empty();
    $("#importPreviewTitle").text(importPreviewTitle + (importedPreviewImages.length ? "（" + importedPreviewImages.length + "）" : ""));
    $("#btnToggleImportPreview")
      .prop("disabled", !importedPreviewImages.length)
      .text(importPreviewPanelOpen ? "收起预览" : "预览导入内容");

    if (!importedPreviewImages.length) {
      $panel.hide();
      return;
    }

    importedPreviewImages.forEach(function (img, index) {
      $grid.append(
        '<button type="button" class="import-preview-item" data-import-preview-index="' + index + '">' +
          '<span class="import-preview-number">' + (index + 1) + '</span>' +
          '<img class="import-preview-thumb" src="' + escAttr(img.url) + '" alt="' + escAttr(img.name || "") + '" loading="lazy" />' +
          '<span class="import-preview-caption">' + escHtml(img.name || ("预览 " + (index + 1))) + '</span>' +
        '</button>'
      );
    });

    $panel.toggle(importPreviewPanelOpen);
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
    $scope.find(".slide-callout").each(function () {
      var $box = $(this);
      var $content = $box.find(".slide-callout-content").first();
      var $preview = $box.find(".slide-callout-preview").first();
      if ($content.length && $preview.length) {
        renderMathText($preview, $content.val() || "", {
          displayMode: false,
          boxedMath: false,
          emptyText: "",
        });
        $preview.css({
          fontSize: $content.css("font-size"),
          textAlign: $content.css("text-align"),
        });
      }
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
    if (title && !$("#customRequirements").val().trim()) {
      $("#customRequirements").val("Title: " + title);
    }
  }

  function applyImportedMarkdownSource(data) {
    var files = data.files || [];
    var content = data.content || "";
    var title = data.filename || (files[0] || "knowledge_graph");
    selectedMarkdownSectionIds = {};
    activeMarkdownPreviewIndex = 0;
    importedMarkdownFiles = [{
      name: title,
      path: title,
      content: content,
      charCount: data.char_count || content.length,
      sections: parseMarkdownSections(content, title),
      expanded: true,
    }];
    refreshMergedMarkdownContent();
    renderMarkdownImportList();
    if (title && !$("#customRequirements").val().trim()) {
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
      missing_equations: Array.isArray(slidesData.missing_equations) ? slidesData.missing_equations : [],
    };
  }

  function renderEquationSourcePanel() {
    var $panel = $("#equationSourcePanel");
    var $missingList = $("#equationMissingList");
    var $list = $("#equationSourceList");
    var $extraList = $("#equationSourceExtraList");
    refreshMissingEquationCatalog();
    $missingList.empty();
    $list.empty();
    $extraList.empty();

    if (!missingEquationCatalog.length) {
      $missingList.append('<div class="equation-source-empty">当前未识别到缺失公式。若页面中有“缺失公式”提示，请先解析或同步 LaTeX。</div>');
    } else {
      missingEquationCatalog.forEach(function (eq) {
        var number = eq.number ? ("(" + eq.number + ")") : (eq.label || eq.key || "缺失公式");
        var hint = eq.chapterHint ? '<div class="equation-source-section">' + escHtml(eq.chapterHint) + '</div>' : "";
        var context = eq.context ? '<div class="equation-source-section">来源：' + escHtml(eq.context) + '</div>' : "";
        $missingList.append(
          '<div class="equation-source-item equation-source-missing-item">' +
            '<div class="equation-source-main">' +
              '<div class="equation-source-meta">' +
                '<span class="equation-source-number">' + escHtml(number) + '</span>' +
              '</div>' +
              '<div class="equation-source-preview">' + escHtml(eq.label || eq.key || number) + '</div>' +
              hint +
              context +
            '</div>' +
          '</div>'
        );
      });
    }

    if (!importedEquationCatalog.length) {
      $("#equationSourceSummary").text(
        "当前缺失 " + missingEquationCatalog.length + " 个公式；请选择包含对应编号的公式章节文件。"
      );
      $list.append('<div class="equation-source-empty">未在文件中识别到编号公式。</div>');
    } else {
      $("#equationSourceSummary").text("当前缺失 " + missingEquationCatalog.length + " 个公式；识别到 " + (importedEquationCatalog.length + extraEquationCatalog.length) + " 个公式；当前章节可引用 " + importedEquationCatalog.length + " 个，非本章缺失 " + extraEquationCatalog.length + " 个");
      importedEquationCatalog.forEach(function (eq, idx) {
        var $row = $(
          '<label class="equation-source-item">' +
            '<input type="checkbox" class="equation-source-check" data-equation-index="' + idx + '" />' +
            '<div class="equation-source-main">' +
              '<div class="equation-source-meta">' +
                '<span class="equation-source-number">(' + escHtml(eq.number || String(idx + 1)) + ')</span>' +
                '<span class="equation-source-section">' + escHtml(eq.section || "") + '</span>' +
              '</div>' +
              '<div class="equation-source-preview"></div>' +
            '</div>' +
          '</label>'
        );
        appendKatexNode($row.find(".equation-source-preview"), eq.formula, true, eq.formula);
        $list.append($row);
      });
    }
    if (!extraEquationCatalog.length) {
      $extraList.append('<div class="equation-source-empty">没有识别到非本章缺失公式。</div>');
    } else {
      extraEquationCatalog.forEach(function (eq, idx) {
        var $row = $(
          '<div class="equation-source-item equation-source-extra-item">' +
            '<div class="equation-source-main">' +
              '<div class="equation-source-meta">' +
                '<span class="equation-source-number">(' + escHtml(eq.number || String(idx + 1)) + ')</span>' +
                '<span class="equation-source-section">' + escHtml(eq.section || "") + '</span>' +
              '</div>' +
              '<div class="equation-source-preview"></div>' +
            '</div>' +
          '</div>'
        );
        appendKatexNode($row.find(".equation-source-preview"), eq.formula, true, eq.formula);
        $extraList.append($row);
      });
    }
    $panel.css("display", "flex");
  }

  function renderSupplementChapterPanel() {
    var $panel = $("#supplementChapterPanel");
    var $list = $("#supplementChapterList");
    $list.empty();
    if (!supplementChapterCatalog.length) {
      $("#supplementChapterSummary").text("未识别到可添加的补充章节");
      $list.append('<div class="equation-source-empty">未在文件中识别到 001 / 001.002 编号章节。</div>');
    } else {
      var files = {};
      supplementChapterCatalog.forEach(function (chapter) {
        files[chapter.fileName || "补充章节"] = true;
      });
      $("#supplementChapterSummary").text(
        "识别到 " + supplementChapterCatalog.length + " 个补充章节，来自 " + Object.keys(files).length + " 个文件"
      );
      supplementChapterCatalog.forEach(function (chapter, idx) {
        var preview = chapter.expanded
          ? '<div class="supplement-chapter-preview">' + escHtml((chapter.content || "").slice(0, 900)) + ((chapter.content || "").length > 900 ? "..." : "") + '</div>'
          : "";
        $list.append(
          '<label class="equation-source-item supplement-chapter-item">' +
            '<input type="checkbox" class="supplement-chapter-check" data-supplement-index="' + idx + '" />' +
            '<div class="equation-source-main">' +
              '<div class="supplement-chapter-row">' +
                '<button type="button" class="supplement-chapter-toggle" data-supplement-index="' + idx + '" aria-expanded="' + (chapter.expanded ? "true" : "false") + '">' +
                  (chapter.expanded ? "收起" : "展开") +
                '</button>' +
                '<div class="equation-source-meta">' +
                  '<span class="equation-source-number">' + escHtml(chapter.number || String(idx + 1)) + '</span>' +
                  '<span class="equation-source-section">' + escHtml(chapter.title || "") + '</span>' +
                  '<span class="supplement-chapter-file">' + escHtml(chapter.fileName || "") + '</span>' +
                '</div>' +
              '</div>' +
              preview +
            '</div>' +
          '</label>'
        );
      });
    }
    $panel.css("display", "flex");
  }

  function addSupplementChaptersToMarkdown(selected) {
    selected = selected || [];
    if (!selected.length) {
      setStatus("请先勾选要添加的补充章节", "error");
      return;
    }
    var hadExplicitSelection = getSelectedMarkdownSections().length > 0;
    var newFileIndex = importedMarkdownFiles.length;
    var titleParts = {};
    selected.forEach(function (chapter) {
      titleParts[chapter.fileName || "补充章节"] = true;
    });
    var sourceTitle = "补充章节：" + Object.keys(titleParts).join("、");
    var sections = selected.map(function (chapter, sectionIndex) {
      return {
        id: markdownSectionId(newFileIndex, sectionIndex),
        title: chapter.title || ("补充章节 " + (sectionIndex + 1)),
        level: 2,
        startLine: chapter.startLine || 1,
        endLine: chapter.endLine || 1,
        content: chapter.content || "",
        expanded: false,
      };
    });
    var content = sections.map(function (section) {
      return section.content || "";
    }).join("\n\n---\n\n");
    importedMarkdownFiles.push({
      name: sourceTitle,
      path: sourceTitle,
      content: content,
      charCount: content.length,
      sections: sections,
      expanded: true,
      sourceType: "supplement",
    });
    if (hadExplicitSelection) {
      sections.forEach(function (section) {
        selectedMarkdownSectionIds[section.id] = true;
      });
    }
    activeMarkdownPreviewIndex = newFileIndex;
    refreshMergedMarkdownContent();
    renderMarkdownImportList();
    $("#supplementChapterPanel").hide();
    setStatus("已添加 " + sections.length + " 个补充章节到 Markdown 生成内容", "success");
  }

  function insertFormulaBoxesFromCatalog(selected) {
    if (!slidesData || currentSlideIdx < 0 || !slidesData.slides[currentSlideIdx]) {
      setStatus("请先生成或打开一个可编辑 PPT 页面", "error");
      return;
    }
    selected = selected || [];
    if (!selected.length) {
      setStatus("请先勾选要引用的公式", "error");
      return;
    }
    saveCurrentSlide();
    var slide = slidesData.slides[currentSlideIdx];
    if (!Array.isArray(slide.formulaBoxes)) slide.formulaBoxes = [];
    selected.forEach(function (eq, offset) {
      var idx = slide.formulaBoxes.length;
      slide.formulaBoxes.push({
        formula: latexMathDisplaySource(eq.formula || ""),
        number: eq.number || "",
        label: eq.label || "",
        x: 120 + (idx + offset) * 18,
        y: 178 + (idx + offset) * 18,
        width: 520,
        height: 96,
        fontSize: 18,
      });
    });
    renderSlideEditor(slide);
    renderSlideList();
    commitHistorySnapshot(false);
    scheduleLatexSync();
    setActiveTab("ppt");
    setStatus("已引用 " + selected.length + " 个公式到当前 PPT 页", "success");
  }

  function waitForSlideImages($root) {
    var images = $root.find("img").toArray();
    if (!images.length) return Promise.resolve();
    var waits = images.map(function (img) {
      if (!img || img.complete) return Promise.resolve();
      return new Promise(function (resolve) {
        var done = function () {
          img.onload = null;
          img.onerror = null;
          resolve();
        };
        img.onload = done;
        img.onerror = done;
        setTimeout(done, 3000);
      });
    });
    return Promise.all(waits).then(function () {});
  }

  function waitForBrowserPaint($root) {
    return new Promise(function (resolve) {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          var fontReady = document.fonts && document.fonts.ready ? document.fonts.ready.catch(function () {}) : Promise.resolve();
          waitForSlideImages($root).then(function () {
            return fontReady;
          }).then(function () {
            setTimeout(resolve, 80);
          });
        });
      });
    });
  }

  function captureRenderedSlideImage(pageIndex) {
    if (!window.html2canvas) {
      return Promise.reject(new Error("网页截图组件未加载，请刷新页面后重试"));
    }
    var $render = $("#slideCanvas .slide-render").first();
    if (!$render.length) return Promise.reject(new Error("未找到当前 PPT 页面"));
    $render.find("[data-math-row]").removeClass("is-editing");
    updateScopedMathPreviews($render);
    clearPptSyncHighlights();
    return waitForBrowserPaint($render).then(function () {
      var node = $render[0];
      return window.html2canvas(node, {
        backgroundColor: "#ffffff",
        scale: 2,
        useCORS: true,
        allowTaint: false,
        logging: false,
        width: node.offsetWidth,
        height: node.offsetHeight,
        scrollX: 0,
        scrollY: 0,
      });
    }).then(function (canvas) {
      return {
        page_index: pageIndex,
        image: canvas.toDataURL("image/png"),
        width: canvas.width,
        height: canvas.height,
      };
    });
  }

  function buildRenderedSlideSnapshots() {
    if (!slidesData || !Array.isArray(slidesData.slides) || !slidesData.slides.length) {
      return Promise.resolve([]);
    }
    var originalIndex = currentSlideIdx;
    var snapshots = [];
    saveCurrentSlide();
    $("body").addClass("ppt-exporting");

    function restoreEditor() {
      $("body").removeClass("ppt-exporting");
      if (originalIndex >= 0 && originalIndex < slidesData.slides.length) {
        currentSlideIdx = originalIndex;
        renderSlideList();
        renderSlideEditor(slidesData.slides[currentSlideIdx]);
        selectLatexSyncForSlide(currentSlideIdx);
      }
    }

    var chain = Promise.resolve();
    slidesData.slides.forEach(function (slide, index) {
      chain = chain.then(function () {
        currentSlideIdx = index;
        $(".slide-thumb").removeClass("active").eq(index).addClass("active");
        renderSlideEditor(slide);
        return captureRenderedSlideImage(index).then(function (snapshot) {
          snapshots.push(snapshot);
          setStatus("正在捕获 PPT 页面 " + (index + 1) + " / " + slidesData.slides.length + "...", "info");
        });
      });
    });

    return chain.then(function () {
      restoreEditor();
      return snapshots;
    }, function (err) {
      restoreEditor();
      throw err;
    });
  }

  function removeLegacySavedPptLoadButton() {
    $("#btnLoadSavedSlide").remove();
    $("#savedPptSlideSelect").remove();
    $(".saved-ppt-tools button").filter(function () {
      return ($(this).text() || "").trim() === "调用此页";
    }).remove();
  }

  function renderSavedPptProjects() {
    removeLegacySavedPptLoadButton();
    var $chapter = $("#savedPptChapterSelect");
    var $chapterList = $("#savedPptChapterList");
    var $chapterToggle = $("#btnSavedPptChapterToggle");
    var selectedId = null;
    if (selectedSavedPptProjectIndex !== null && !savedPptProjects[selectedSavedPptProjectIndex]) {
      selectedSavedPptProjectIndex = null;
    }
    if ($chapterList.length) {
      $chapterList.empty();
    }
    if ($chapter.length) {
      selectedId = selectedSavedPptProjectIndex !== null && savedPptProjects[selectedSavedPptProjectIndex]
        ? savedPptProjects[selectedSavedPptProjectIndex].chapter_id
        : "";
      $chapter.empty().append('<option value="">选择章节</option>');
      for (var i = 0; i < savedPptProjects.length; i++) {
        var project = savedPptProjects[i] || {};
        var label = project.chapter_title || project.title || project.chapter_id || ("章节 " + (i + 1));
        var count = parseInt(project.slide_count, 10);
        if (Number.isNaN(count) && Array.isArray(project.slides)) count = project.slides.length;
        var suffix = Number.isNaN(count) ? "" : ("（" + count + "页）");
        $chapter.append('<option value="' + i + '">' + escHtml(label + suffix) + '</option>');
        if ($chapterList.length) {
          $chapterList.append(
            '<div class="saved-ppt-chapter-row' + (selectedSavedPptProjectIndex === i ? " active" : "") + '" data-project-index="' + i + '">' +
              '<button type="button" class="saved-ppt-chapter-open" title="' + escAttr(label + suffix) + '">' + escHtml(label + suffix) + '</button>' +
              '<button type="button" class="saved-ppt-chapter-remove" title="删除该章节 PPT" aria-label="删除' + escAttr(label) + '" data-project-index="' + i + '">&times;<span>删除</span></button>' +
            '</div>'
          );
        }
      }
      if (selectedId) {
        for (var j = 0; j < savedPptProjects.length; j++) {
          if ((savedPptProjects[j] || {}).chapter_id === selectedId) {
            selectedSavedPptProjectIndex = j;
            $chapter.val(String(j));
            break;
          }
        }
      }
      $chapter.prop("disabled", !savedPptProjects.length);
    }
    if ($chapterToggle.length) {
      var countText = savedPptProjects.length ? "（" + savedPptProjects.length + "）" : "";
      $chapterToggle.text("选择已保存章节" + countText);
      $chapterToggle.prop("disabled", false);
    }
    if ($chapterList.length && !savedPptProjects.length) {
      $chapterList.html(
        '<div class="saved-ppt-chapter-empty">' +
          escHtml(savedPptLoadError || "暂无已保存章节，点击“刷新”重新读取。") +
        '</div>'
      );
    }
    $("#savedPptSlideGallery").empty().hide();
  }

  function fetchSavedPptProjectsJson() {
    var paths = ["/beamer-generator/api/saved-projects", "/beamer-generator/api/saved-projects/", "/api/saved-projects"];
    var index = 0;
    function tryNext(lastErr) {
      if (index >= paths.length) return Promise.reject(lastErr || new Error("未找到已保存 PPT 接口"));
      var separator = paths[index].indexOf("?") >= 0 ? "&" : "?";
      var url = paths[index++] + separator + "_=" + Date.now();
      return fetch(url, {
        cache: "no-store",
        headers: {
          "Accept": "application/json",
          "Cache-Control": "no-cache"
        }
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

  function upsertSavedPptProject(project) {
    if (!project || !project.chapter_id) return;
    var next = {
      chapter_id: project.chapter_id,
      chapter_title: project.chapter_title || project.title || project.chapter_id,
      title: project.title || project.chapter_title || project.chapter_id,
      updated_at: project.updated_at || new Date().toISOString(),
      slide_count: parseInt(project.slide_count, 10) || 0,
      slides: Array.isArray(project.slides) ? project.slides : []
    };
    var found = -1;
    for (var i = 0; i < savedPptProjects.length; i++) {
      if ((savedPptProjects[i] || {}).chapter_id === next.chapter_id) {
        found = i;
        break;
      }
    }
    if (found >= 0) {
      savedPptProjects.splice(found, 1);
    }
    savedPptProjects.unshift(next);
    selectedSavedPptProjectIndex = 0;
    renderSavedPptProjects();
  }

  function loadSavedPptProjects(options) {
    options = options || {};
    var selectedChapterId = options.selectedChapterId || "";
    $("#savedPptChapterSelect").prop("disabled", true);
    $("#btnSavedPptChapterToggle").prop("disabled", false).text("选择已保存章节");
    $("#btnRefreshSavedPpt").prop("disabled", true).text("刷新中...");
    return fetchSavedPptProjectsJson()
      .then(function (data) {
        savedPptLoadError = "";
        savedPptProjects = Array.isArray(data.projects) ? data.projects : [];
        if (selectedChapterId) {
          for (var i = 0; i < savedPptProjects.length; i++) {
            if ((savedPptProjects[i] || {}).chapter_id === selectedChapterId) {
              selectedSavedPptProjectIndex = i;
              break;
            }
          }
        }
        renderSavedPptProjects();
        setStatus("已读取保存内容，共 " + savedPptProjects.length + " 个章节", "success");
      })
      .catch(function (err) {
        savedPptLoadError = "读取保存章节失败：" + err.message;
        savedPptProjects = [];
        renderSavedPptProjects();
        setStatus("读取保存内容失败: " + err.message, "error");
      })
      .finally(function () {
        $("#btnRefreshSavedPpt").prop("disabled", false).text("刷新");
        renderSavedPptProjects();
        if (options.openAfterLoad) {
          setSavedPptChapterListOpen(true);
        }
        if (selectedChapterId && selectedSavedPptProjectIndex !== null && savedPptProjects[selectedSavedPptProjectIndex]) {
          $("#savedPptChapterSelect").val(String(selectedSavedPptProjectIndex));
          selectSavedPptProject(selectedSavedPptProjectIndex);
        }
      });
  }

  function deleteSavedPptProject(projectIndex) {
    var project = savedPptProjects[projectIndex];
    if (!project || !project.chapter_id) return Promise.reject(new Error("未选择保存章节"));
    var paths = [
      "/beamer-generator/api/saved-projects/" + encodeURIComponent(project.chapter_id),
      "/api/saved-projects/" + encodeURIComponent(project.chapter_id)
    ];
    var index = 0;
    function tryNext(lastErr) {
      if (index >= paths.length) return Promise.reject(lastErr || new Error("未找到删除接口"));
      var url = paths[index++];
      return fetch(url, {
        method: "DELETE",
        cache: "no-store",
        headers: { "Accept": "application/json" }
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

  function setSavedPptChapterListOpen(open) {
    $("#savedPptChapterList").toggleClass("open", !!open);
    $("#btnSavedPptChapterToggle").attr("aria-expanded", open ? "true" : "false");
  }

  function confirmAndDeleteSavedPpt(projectIndex) {
    var project = savedPptProjects[projectIndex];
    if (Number.isNaN(projectIndex) || !project) {
      setStatus("请先选择要删除的 PPT 章节", "error");
      return;
    }
    var label = project.chapter_title || project.title || project.chapter_id || "该章节";
    if (!window.confirm("是否确认删除该章节 PPT？\n\n" + label)) return;
    setStatus("正在删除已保存 PPT：" + label, "info");
    deleteSavedPptProject(projectIndex)
      .then(function () {
        savedPptProjects.splice(projectIndex, 1);
        selectedSavedPptProjectIndex = null;
        $("#savedPptSlideGallery").empty().hide();
        renderSavedPptProjects();
        return loadSavedPptProjects({ openAfterLoad: true }).then(function () {
          setSavedPptChapterListOpen(true);
        });
      })
      .then(function () {
        setStatus("已删除已保存 PPT：" + label, "success");
      })
      .catch(function (err) {
        setStatus("删除已保存 PPT 失败: " + err.message, "error");
        renderSavedPptProjects();
      });
  }

  function selectSavedPptProject(projectIndex) {
    if (Number.isNaN(projectIndex) || !savedPptProjects[projectIndex]) {
      selectedSavedPptProjectIndex = null;
      $("#savedPptSlideGallery").empty().hide();
      renderSavedPptProjects();
      return;
    }
    selectedSavedPptProjectIndex = projectIndex;
    renderSavedPptProjects();
    renderSavedPptSlides(projectIndex);
    showSavedPptGalleryMessage("正在加载页面...", "已保存章节页面");
    savedPptProjectData(projectIndex)
      .then(function (projectData) {
        renderSavedPptSlides(projectIndex);
        renderSavedPptGallery(projectIndex, projectData);
      })
      .catch(function (err) {
        showSavedPptGalleryMessage("加载页面失败：" + err.message, "已保存章节页面");
      });
  }

  function savedPptProjectData(projectIndex) {
    var project = savedPptProjects[projectIndex];
    if (!project || !project.chapter_id) return Promise.reject(new Error("未选择保存章节"));
    if (project.fullData && Array.isArray(project.fullData.slides)) return Promise.resolve(project.fullData);
    var paths = [
      "/beamer-generator/api/saved-projects/" + encodeURIComponent(project.chapter_id),
      "/api/saved-projects/" + encodeURIComponent(project.chapter_id)
    ];
    var index = 0;
    function tryNext(lastErr) {
      if (index >= paths.length) return Promise.reject(lastErr || new Error("未找到保存章节"));
      var separator = paths[index].indexOf("?") >= 0 ? "&" : "?";
      var url = paths[index++] + separator + "_=" + Date.now();
      return fetch(url, {
        cache: "no-store",
        headers: {
          "Accept": "application/json",
          "Cache-Control": "no-cache"
        },
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
    return tryNext()
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

  function miniPct(value, total, fallback) {
    var n = Number(value);
    if (Number.isNaN(n)) n = Number(fallback) || 0;
    return (Math.max(0, Math.min(total, n)) / total * 100).toFixed(2) + "%";
  }

  function miniBoxStyle(box, fallback) {
    box = box || {};
    fallback = fallback || {};
    var width = clampNumber(Number(box.width), 24, SLIDE_DESIGN_WIDTH, Number(fallback.width) || 220);
    var height = clampNumber(Number(box.height), 18, SLIDE_DESIGN_HEIGHT, Number(fallback.height) || 120);
    var x = clampNumber(Number(box.x), 0, Math.max(0, SLIDE_DESIGN_WIDTH - width), Number(fallback.x) || 0);
    var y = clampNumber(Number(box.y), 0, Math.max(0, SLIDE_DESIGN_HEIGHT - height), Number(fallback.y) || 0);
    return [
      "left:" + miniPct(x, SLIDE_DESIGN_WIDTH, 0),
      "top:" + miniPct(y, SLIDE_DESIGN_HEIGHT, 0),
      "width:" + miniPct(width, SLIDE_DESIGN_WIDTH, 100),
      "height:" + miniPct(height, SLIDE_DESIGN_HEIGHT, 60)
    ].join(";");
  }

  function miniMathText(text, className, richHtml, attrs) {
    return '<div class="kg-mini-math-text ' + (className || "") + '"' +
      ' data-mini-text="' + escAttr(repairPptLatexArtifacts(text || "")) + '"' +
      ' data-rich-html="' + escAttr(richHtml || "") + '"' +
      (attrs || "") + '></div>';
  }

  function renderSlideMiniature(slide, pageIndex, className) {
    slide = slide || {};
    var renderedBg = slide.renderedBackground || "";
    var items = Array.isArray(slide.items) ? slide.items : [];
    var itemRichHtml = Array.isArray(slide.itemRichHtml) ? slide.itemRichHtml : [];
    var equations = Array.isArray(slide.equations) ? slide.equations : [];
    var missingEquations = Array.isArray(slide.missing_equations) ? slide.missing_equations : [];
    var placeholders = normalizePlaceholders(slide.placeholders || []);
    var images = Array.isArray(slide.images) ? slide.images : [];
    var textboxes = Array.isArray(slide.textboxes) ? slide.textboxes : [];
    var callouts = Array.isArray(slide.callouts) ? slide.callouts : [];
    var formulaBoxes = Array.isArray(slide.formulaBoxes) ? slide.formulaBoxes : [];
    var hasRightPlaceholder = placeholders.some(function (ph) {
      return (parseFloat(ph && ph.x) || 0) >= 430;
    });
    var hasVisibleContent = (slide.title || slide.subtitle || items.length || equations.length || formulaBoxes.length || missingEquations.length ||
      placeholders.length || images.length || textboxes.length || callouts.length ||
      (slide.table && slide.table.headers));

    var html = '<div class="kg-slide-miniature ' + (className || "") + (slide.reviewBackground ? " review-background" : "") + (renderedBg ? " has-rendered-background" : "") + '">' +
      '<div class="kg-mini-stage">' +
        (renderedBg ? '<img class="kg-mini-rendered-background" src="' + escAttr(renderedBg) + '" alt="" />' : '') +
        '<div class="kg-mini-topline"></div>' +
        '<div class="kg-mini-page">第 ' + (pageIndex + 1) + ' 页</div>' +
        '<div class="kg-mini-title-zone">' +
          miniMathText(slide.title || "未命名页面", "kg-mini-title", slide.titleRichHtml || "") +
        '</div>' +
        '<div class="kg-mini-subtitle-zone">' +
          miniMathText(slide.subtitle || "", "kg-mini-subtitle", slide.subtitleRichHtml || "") +
        '</div>' +
        (slide.type === "title" && slide.titleCredit
          ? '<div class="kg-mini-title-credit">' + miniMathText(slide.titleCredit || "", "kg-mini-credit-text", "") + '</div>'
          : '') +
        '<div class="kg-mini-body' + (hasRightPlaceholder ? " has-right-figure" : "") + (slide.hideParsedContent ? " is-hidden" : "") + '">';

    if (items.length) {
      html += '<ul class="kg-mini-items">';
      items.forEach(function (item, idx) {
        html += '<li><span class="kg-mini-bullet">•</span>' +
          miniMathText(item || "", "kg-mini-item-text", itemRichHtml[idx] || "") +
          '</li>';
      });
      html += '</ul>';
    }

    if (equations.length) {
      html += '<div class="kg-mini-equations">';
      equations.forEach(function (eq) {
        html += miniMathText(eq || "", "kg-mini-equation", "", ' data-display-math="true"');
      });
      html += '</div>';
    }

    if (formulaBoxes.length) {
      html += '<div class="kg-mini-formula-boxes">';
      formulaBoxes.forEach(function (box) {
        html += '<div class="kg-mini-free-formula" style="' + miniBoxStyle(box, { width: 360, height: 80 }) + '">' +
          miniMathText((box && box.formula) || "", "kg-mini-equation", "", ' data-display-math="true"') +
          '</div>';
      });
      html += '</div>';
    }

    if (missingEquations.length) {
      html += '<div class="kg-mini-missing-equations">';
      missingEquations.forEach(function (eq) {
        var label = (eq && (eq.label || eq.key)) || "Unknown equation";
        html += '<div class="kg-mini-missing-equation">缺失公式：' + escHtml(label) + '</div>';
      });
      html += '</div>';
    }

    if (slide.table && slide.table.headers) {
      var table = normalizeTable(slide.table);
      html += '<table class="kg-mini-table"><thead><tr>';
      (table.headers || []).forEach(function (header, idx) {
        html += '<th>' + miniMathText(header || "", "kg-mini-table-text", (table.headerRichHtml || [])[idx] || "") + '</th>';
      });
      html += '</tr></thead><tbody>';
      (table.rows || []).forEach(function (row, rowIdx) {
        html += '<tr>';
        row.forEach(function (cell, cellIdx) {
          html += '<td>' + miniMathText(cell || "", "kg-mini-table-text", ((table.rowRichHtml || [])[rowIdx] || [])[cellIdx] || "") + '</td>';
        });
        html += '</tr>';
      });
      html += '</tbody></table>';
    }

    if (!hasVisibleContent) {
      html += '<div class="kg-mini-empty">空白页</div>';
    }
    html += '</div>';

    html += '<div class="kg-mini-free-layer">';
    placeholders.forEach(function (ph, idx) {
      var phUrl = ph.asset || ph.url || ph.path || "";
      var phStyle = miniBoxStyle(ph, { x: 500 + idx * 12, y: 120 + idx * 12, width: 235, height: 165 });
      if (phUrl) {
        html += '<img class="kg-mini-placeholder-image" style="' + phStyle + '" src="' + escAttr(phUrl) + '" alt="" />';
      } else {
        html += '<div class="kg-mini-placeholder" style="' + phStyle + '">' +
          escHtml(String(ph.label || ph.figure || "图片占位").slice(0, 40)) + '</div>';
      }
    });

    images.forEach(function (img, idx) {
      img = img || {};
      var imgUrl = img.url || img.path || img.src || "";
      if (!imgUrl) return;
      html += '<img class="kg-mini-image" style="' + miniBoxStyle(img, { x: 40 + idx * 16, y: 170 + idx * 12, width: 220, height: 150 }) +
        '" src="' + escAttr(imgUrl) + '" alt="" />';
    });

    textboxes.forEach(function (tb, idx) {
      tb = tb || {};
      var tbStyle = miniBoxStyle(tb, { x: 56 + idx * 18, y: 190 + idx * 22, width: 260, height: 96 });
      var tbColor = toCssColor(tb.color, "#333333");
      var tbBg = toCssColor(tb.bg, "#ffffff");
      var tbFontSize = parseInt(tb.fontSize, 10) || 14;
      html += '<div class="kg-mini-textbox" style="' + tbStyle + ';background:' + escAttr(tbBg) + ';color:' + escAttr(tbColor) +
        ';--mini-text-size-small:' + (tbFontSize * 0.42).toFixed(1) + 'px;--mini-text-size-large:' + tbFontSize + 'px;text-align:' + escAttr(tb.align || "left") + ';">' +
        miniMathText(tb.text || "", "kg-mini-textbox-text", tb.richHtml || "") +
        '</div>';
    });

    callouts.forEach(function (callout, idx) {
      callout = callout || {};
      var calloutFontSize = parseInt(callout.fontSize, 10) || 12;
      html += '<div class="kg-mini-callout" style="' + miniBoxStyle(callout, { x: 130 + idx * 18, y: 178 + idx * 18, width: 250, height: 92 }) +
        ';--mini-text-size-small:' + (calloutFontSize * 0.42).toFixed(1) + 'px;--mini-text-size-large:' + calloutFontSize + 'px;text-align:' + escAttr(callout.align || "center") + ';">' +
        miniMathText(callout.text || "", "kg-mini-callout-text") +
        '</div>';
    });
    html += '</div></div></div>';
    return html;
  }

  function renderSlideMiniatureMath($root) {
    if (!$root || !$root.length) return;
    $root.find(".kg-mini-math-text").each(function () {
      var $target = $(this);
      var text = $target.attr("data-mini-text") || "";
      var richHtml = $target.attr("data-rich-html") || "";
      if (richHtml) {
        restoreRichTextHtml($target, richHtml, text);
        return;
      }
      renderMathText($target, text, {
        displayMode: String($target.attr("data-display-math") || "") === "true",
        boxedMath: false,
        emptyText: "",
      });
    });
  }

  function renderSavedSlideMini(slide, pageIndex, className) {
    return renderSlideMiniature(slide, pageIndex, "saved-slide-mini " + (className || ""));
  }

  function renderSavedSlideMiniMath($root) {
    renderSlideMiniatureMath($root);
  }

  function renderSavedPptGalleryShell($gallery, title) {
    $gallery.empty().append(
      '<button type="button" class="saved-ppt-gallery-close saved-ppt-gallery-floating-close" data-action="close-saved-ppt-gallery" title="关闭已保存 PPT 缩略图" aria-label="关闭已保存 PPT 缩略图">×</button>' +
      '<div class="saved-ppt-gallery-header">' +
        '<div class="saved-ppt-gallery-title-wrap">' +
          '<span class="saved-ppt-gallery-title">' + escHtml(title || "已保存章节页面") + '</span>' +
          '<span class="saved-ppt-gallery-hint">按住缩略图拖到当前 PPT 左侧列表，即可插入到本章节</span>' +
        '</div>' +
        '<button type="button" class="saved-ppt-gallery-close saved-ppt-gallery-inline-close" data-action="close-saved-ppt-gallery" title="关闭预览框" aria-label="关闭已保存章节预览框">×</button>' +
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
    var $actions = $(
      '<div class="saved-ppt-gallery-actions">' +
        '<button type="button" class="btn-primary saved-ppt-use-all" data-action="use-saved-ppt-all">调用整章</button>' +
      '</div>'
    );
    $actions.find("[data-action='use-saved-ppt-all']").on("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      replaceCurrentProjectWithSavedProject(projectData);
    });
    $content.append($actions);
    slides.forEach(function (slide, idx) {
      var $card = $(
        '<button type="button" class="saved-ppt-slide-card" draggable="true" data-page-index="' + idx + '">' +
          renderSavedSlideMini(slide, idx, "") +
          '<span class="saved-ppt-slide-use">调用此页</span>' +
        '</button>'
      );
      renderSavedSlideMiniMath($card);
      $card.on("click", function () {
        insertSavedSlideIntoCurrentProject(slide);
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
    if ($gallery.closest(".saved-ppt-section").length) {
      $gallery.css({ left: "", top: "", width: "", maxHeight: "" });
      savedPptGalleryManualPosition = null;
      return;
    }
    var anchor = $("#savedPptChapterSelect")[0] || $("#btnSaveProject")[0];
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
    var project = savedPptProjects[projectIndex];
    if (!project || !Array.isArray(project.slides) || !project.slides.length) {
      $("#savedPptSlideGallery").empty().hide();
    }
  }

  function loadSavedSlideFromProject(projectIndex, pageIndex) {
    return savedPptProjectData(projectIndex).then(function (projectData) {
      var slides = Array.isArray(projectData.slides) ? projectData.slides : [];
      if (pageIndex < 0 || pageIndex >= slides.length) throw new Error("未找到页面内容");
      return slides[pageIndex];
    });
  }

  function replaceCurrentProjectWithSavedProject(projectData) {
    if (!projectData || !Array.isArray(projectData.slides) || !projectData.slides.length) {
      setStatus("已保存章节没有可调用页面", "error");
      return;
    }
    saveCurrentSlide();
    slidesData = deepClone(projectData);
    if (!Array.isArray(slidesData.slides)) slidesData.slides = [];
    for (var i = 0; i < slidesData.slides.length; i++) {
      slidesData.slides[i].id = i;
      if (!slidesData.slides[i].images) slidesData.slides[i].images = [];
      if (!slidesData.slides[i].textboxes) slidesData.slides[i].textboxes = [];
      if (!slidesData.slides[i].formulaBoxes) slidesData.slides[i].formulaBoxes = [];
      if (!slidesData.slides[i].callouts) slidesData.slides[i].callouts = [];
      slidesData.slides[i].placeholders = normalizePlaceholders(slidesData.slides[i].placeholders);
      if (slidesData.slides[i].table) slidesData.slides[i].table = normalizeTable(slidesData.slides[i].table);
    }
    fullLatex = slidesData.latex || fullLatex || "";
    sourceLatex = fullLatex;
    if (fullLatex) updateLatexEditor(fullLatex);
    currentSlideIdx = slidesData.slides.length ? 0 : -1;
    resetHistory();
    $("#pptChapterTitleInput").val(slidesData.chapter_title || slidesData.title || "");
    $("#tabPpt").prop("disabled", !slidesData.slides.length);
    updateDownloadPptxButton();
    if (hasRenderedLatexPages(slidesData)) {
      inputCollapsed = true;
      localStorage.setItem("bg_input_panel_collapsed", "1");
      rebuildRenderedPageLocationMap(slidesData, fullLatex);
    } else {
      rebuildLatexSyncMapFromSource(slidesData, fullLatex);
    }
    setActiveTab("ppt");
    applyInputCollapsedState();
    renderSlideList();
    if (currentSlideIdx >= 0) selectSlide(currentSlideIdx);
    setStatus("已调用已保存章节：" + (slidesData.chapter_title || slidesData.title || "未命名章节"), "success");
  }

  function insertSavedSlideIntoCurrentProject(slideData, insertIndex) {
    if (!slidesData || !slideData) return;
    if (!Array.isArray(slidesData.slides)) slidesData.slides = [];
    saveCurrentSlide();
    var slide = deepClone(slideData);
    if (!slide.images) slide.images = [];
    if (!slide.textboxes) slide.textboxes = [];
    if (!slide.formulaBoxes) slide.formulaBoxes = [];
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
    if (isGenerating && !(arguments[2] && arguments[2].generation)) {
      queuedStatusMessage = { msg: msg, type: type };
      return;
    }
    if (isGenerating && (arguments[2] && arguments[2].generation)) {
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
    if (msg) latexGenerateStatusMessage = msg;
    setStatus(msg, "info", { generation: true });
  }

  function setOutlineProgress(value, message, state) {
    outlineGenerateProgress = Math.max(0, Math.min(100, Math.round(Number(value) || 0)));
    $("#outlineProgressPanel")
      .removeClass("success error")
      .addClass(state === "success" ? "success" : (state === "error" ? "error" : ""))
      .show();
    $("#outlineProgressMessage").text(message || "正在生成纪要...");
    $("#outlineProgressPercent").text(outlineGenerateProgress + "%");
    $("#outlineProgressFill").css("width", outlineGenerateProgress + "%");
  }

  function startOutlineProgress(message) {
    if (outlineProgressTimer) clearInterval(outlineProgressTimer);
    setOutlineProgress(4, message || "正在准备纪要生成请求...");
    outlineProgressTimer = setInterval(function () {
      var next = outlineGenerateProgress;
      if (next < 25) next += 3;
      else if (next < 65) next += 2;
      else if (next < 90) next += 1;
      else next = 90;
      setOutlineProgress(next, "GPT 正在生成大节与每页 frame 纪要...");
      if (next >= 90 && outlineProgressTimer) {
        clearInterval(outlineProgressTimer);
        outlineProgressTimer = null;
      }
    }, 900);
  }

  function finishOutlineProgress(message, state) {
    if (outlineProgressTimer) {
      clearInterval(outlineProgressTimer);
      outlineProgressTimer = null;
    }
    setOutlineProgress(state === "error" ? Math.max(outlineGenerateProgress, 1) : 100, message, state);
  }

  function updateDownloadPptxButton() {
    $("#btnDownloadPptx").prop("disabled", !slidesData || !slidesData.slides || !slidesData.slides.length);
  }

  function updateLatexImportMeta(message) {
    if (!isLatexImportMode) return;
    $("#latexImportMeta").text(message || "导入 LaTeX、PDF 或 Overleaf ZIP 后，将按编译 PDF 页面渲染为 PPT；若源码引用图片或样式文件，请使用项目目录导入。");
  }

  function hasRenderedLatexPages(data) {
    return !!(data && Array.isArray(data.slides) && data.slides.some(function (slide) {
      return slide && slide.latexRenderedPage;
    }));
  }

  function ajaxErrorMessage(xhr, fallback) {
    fallback = fallback || "请求失败";
    if (!xhr) return fallback;
    if (xhr.responseJSON) {
      if (xhr.responseJSON.error) return String(xhr.responseJSON.error);
      if (xhr.responseJSON.detail) {
        if (Array.isArray(xhr.responseJSON.detail)) {
          return xhr.responseJSON.detail.map(function (item) {
            return item && item.msg ? item.msg : JSON.stringify(item);
          }).join("; ");
        }
        return String(xhr.responseJSON.detail);
      }
    }
    var text = String(xhr.responseText || "").trim();
    if (text) {
      try {
        var parsed = JSON.parse(text);
        if (parsed.error) return String(parsed.error);
        if (parsed.detail) return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
      } catch (err) {
        var compact = text.replace(/\s+/g, " ");
        if (compact.length > 180) compact = compact.slice(0, 180) + "...";
        if (compact) return compact;
      }
    }
    if (xhr.status === 404) return "渲染接口不存在，请重启 render_app.py 对应的网站服务后再试";
    if (xhr.status === 413) return "上传/提交内容过大，请改用对应 PDF 文件导入";
    if (xhr.status === 0) return "无法连接后端服务，请确认网站后端已启动";
    if (xhr.status) return "HTTP " + xhr.status;
    return fallback;
  }

  function titleFromLatexFileName(fileName) {
    return String(fileName || "")
      .replace(/\.(tex|latex|txt|pdf)$/i, "")
      .replace(/[_-]+/g, " ")
      .trim();
  }

  function applyLatexImportMode() {
    if (!isLatexImportMode) return;
    $(".panel-input").find(".form-row, #customRequirements, #customRequirements + small, .form-group").hide();
    $("#btnGenerate, #btnGenerateOutline, #outlinePanel, #viewOutline, .api-config-panel, .generate-actions").hide();
    $("#latexImportPanel").addClass("latex-import-panel-inline").insertAfter(".tab-bar").show();
    $("#btnConvertPpt").hide().prop("disabled", true);
    $("#btnDownloadPptx").hide().prop("disabled", true);
    $("#tabPpt").prop("disabled", true);
    $("#tabOutline").prop("disabled", true);
    $(".tab-btn[data-tab='latex']").text("LaTeX 代码");
    $("#slideCanvas").html('<div class="slide-placeholder">导入 PPTX 后，左侧显示转换后的 LaTeX 代码。</div>');
    inputCollapsed = true;
    localStorage.setItem("bg_input_panel_collapsed", "1");
    updateLatexImportMeta();
  }

  function setGenerating(state) {
    isGenerating = state;
    if (state) latexGenerateProgress = 0;
    $("#btnGenerate").prop("disabled", state)
      .text(state ? "生成中..." : "生成 LaTeX");
    $("#btnGenerateOutline").prop("disabled", state)
      .text(state ? "生成中..." : "生成纪要");
    if (!state) {
      var has = !!fullLatex;
      $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf, #btnConvertPpt").prop("disabled", !has);
      updateDownloadPptxButton();
      updateHistoryButtons();
      if (queuedStatusMessage) {
        var queued = queuedStatusMessage;
        queuedStatusMessage = null;
        setStatus(queued.msg, queued.type);
      }
    } else {
      $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf, #btnConvertPpt, #btnDownloadPptx").prop("disabled", true);
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

  $("#savedPptChapterSelect").on("change", function () {
    var index = parseInt($(this).val(), 10);
    if (Number.isNaN(index) || !savedPptProjects[index]) {
      selectedSavedPptProjectIndex = null;
      $("#savedPptSlideGallery").empty().hide();
      renderSavedPptProjects();
      return;
    }
    selectSavedPptProject(index);
  });

  $("#btnSavedPptChapterToggle").on("click", function (e) {
    e.preventDefault();
    e.stopPropagation();
    setSavedPptChapterListOpen(!$("#savedPptChapterList").hasClass("open"));
  });

  $("#savedPptChapterList").on("click", ".saved-ppt-chapter-open", function (e) {
    e.preventDefault();
    e.stopPropagation();
    var index = parseInt($(this).closest(".saved-ppt-chapter-row").attr("data-project-index"), 10);
    if (Number.isNaN(index) || !savedPptProjects[index]) return;
    $("#savedPptChapterSelect").val(String(index));
    setSavedPptChapterListOpen(false);
    selectSavedPptProject(index);
  });

  $("#savedPptChapterList").on("click", ".saved-ppt-chapter-remove", function (e) {
    e.preventDefault();
    e.stopPropagation();
    var index = parseInt($(this).attr("data-project-index"), 10);
    if (Number.isNaN(index)) {
      index = parseInt($(this).closest(".saved-ppt-chapter-row").attr("data-project-index"), 10);
    }
    confirmAndDeleteSavedPpt(index);
  });

  $(document).on("click.savedPptChapterList", function (e) {
    if ($(e.target).closest(".saved-ppt-section").length) return;
    setSavedPptChapterListOpen(false);
  });

  $("#btnRefreshSavedPpt").on("click", function (e) {
    e.preventDefault();
    e.stopPropagation();
    loadSavedPptProjects({ openAfterLoad: true });
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
    if ($(this).closest(".saved-ppt-section").length) return;
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

  $("#btnImportSupplementMarkdown").on("click", function () {
    $("#supplementMarkdownImporter").val("").trigger("click");
  });

  $("#btnImportGraphPackage").on("click", function () {
    $("#graphPackageImporter").val("").trigger("click");
  });

  function setLatexImportLoading(state) {
    $("#btnImportPptInLatexPanel").prop("disabled", state).text(state ? "导入中..." : "导入 PPTX 转 LaTeX");
  }

  $("#btnImportEquationSource").on("click", function () {
    renderEquationSourcePanel();
    setStatus("已列出当前缺失公式目录，请按编号选择并导入对应公式章节。", missingEquationCatalog.length ? "success" : "error");
  });

  $("#btnChooseEquationSourceFile").on("click", function () {
    $("#equationSourceImporter").val("").trigger("click");
  });

  $("#btnImportPptLatex").on("click", function () {
    $("#pptLatexImporter").val("").trigger("click");
  });

  $("#btnImportPptInLatexPanel").on("click", function () {
    $("#pptLatexImporter").val("").trigger("click");
  });

  $("#btnCloseEquationSourcePanel").on("click", function () {
    $("#equationSourcePanel").hide();
  });

  $("#btnCloseSupplementChapterPanel").on("click", function () {
    $("#supplementChapterPanel").hide();
  });

  $("#btnReferenceSelectedEquations").on("click", function () {
    var selected = [];
    $("#equationSourceList .equation-source-check:checked").each(function () {
      var idx = parseInt($(this).data("equation-index"), 10);
      if (!Number.isNaN(idx) && importedEquationCatalog[idx]) selected.push(importedEquationCatalog[idx]);
    });
    insertFormulaBoxesFromCatalog(selected);
  });

  $("#supplementChapterList").on("click", ".supplement-chapter-toggle", function (e) {
    e.preventDefault();
    e.stopPropagation();
    var idx = parseInt($(this).data("supplement-index"), 10);
    if (Number.isNaN(idx) || !supplementChapterCatalog[idx]) return;
    supplementChapterCatalog[idx].expanded = !supplementChapterCatalog[idx].expanded;
    renderSupplementChapterPanel();
  });

  $("#btnAddSelectedSupplementChapters").on("click", function () {
    var selected = [];
    $("#supplementChapterList .supplement-chapter-check:checked").each(function () {
      var idx = parseInt($(this).data("supplement-index"), 10);
      if (!Number.isNaN(idx) && supplementChapterCatalog[idx]) selected.push(supplementChapterCatalog[idx]);
    });
    addSupplementChaptersToMarkdown(selected);
  });

  function resolveMissingEquationsFromSource(sourceText, fileName) {
    var split = splitEquationCatalogForCurrentChapter(extractEquationCatalog(sourceText || "", fileName || ""));
    importedEquationCatalog = split.matched;
    extraEquationCatalog = split.extra;
    renderEquationSourcePanel();
    $("#equationSourceImporter").val("");
    if (importedEquationCatalog.length || extraEquationCatalog.length) {
      setStatus("公式章节识别完成：当前章节可引用 " + importedEquationCatalog.length + " 个，非本章缺失 " + extraEquationCatalog.length + " 个。未修改 LaTeX 代码。", "success");
    } else {
      setStatus("未在公式章节中识别到公式，LaTeX 代码未改变", "error");
    }
  }

  $("#btnTogglePackageImages").on("click", function () {
    if (!importedPackageImages.length) return;
    packageImagePanelOpen = !packageImagePanelOpen;
    renderPackageImages();
  });

  $("#btnToggleImportPreview").on("click", function () {
    if (!importedPreviewImages.length) return;
    importPreviewPanelOpen = !importPreviewPanelOpen;
    renderImportPreviewPanel();
  });

  $("#importPreviewPanel").on("click", "[data-action='close-import-preview']", function (e) {
    e.preventDefault();
    importPreviewPanelOpen = false;
    renderImportPreviewPanel();
  });

  $("#importPreviewGrid").on("click", ".import-preview-item", function () {
    var index = parseInt($(this).data("import-preview-index"), 10);
    if (Number.isNaN(index) || !importedPreviewImages[index]) return;
    openPackageImageViewer(importedPreviewImages[index], index);
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
    var files = Array.prototype.slice.call(this.files || []);
    if (!files.length) return;

    var markdownFiles = files.filter(function (file) {
      return /\.(md|markdown)$/i.test(file.name || "") ||
        /markdown/i.test(file.type || "");
    });
    if (!markdownFiles.length) {
      setStatus("请选择 .md 或 .markdown 知识图谱文件", "error");
      $(this).val("");
      return;
    }

    $("#btnImportMarkdown").prop("disabled", true).text("导入中...");
    var startIndex = importedMarkdownFiles.length;
    markdownFiles.map(function (file) {
      return {
        name: file.name || "知识图谱",
        path: markdownFileDisplayPath(file),
        content: "",
        charCount: 0,
        sections: [],
        expanded: false,
      };
    }).forEach(function (item) {
      importedMarkdownFiles.push(item);
    });
    renderMarkdownImportList();
    setStatus("正在导入 " + markdownFiles.length + " 个知识图谱文件...", "info");

    Promise.all(markdownFiles.map(function (file, index) {
      var targetIndex = startIndex + index;
      return importMarkdownFile(file)
        .then(function (item) {
          importedMarkdownFiles[targetIndex] = item;
          renderMarkdownImportList();
          return item;
        })
        .catch(function (err) {
          importedMarkdownFiles[targetIndex] = {
            name: file.name || "知识图谱",
            path: markdownFileDisplayPath(file),
            content: "",
            charCount: 0,
            sections: [],
            expanded: false,
            error: err.message || "请求失败",
          };
          renderMarkdownImportList();
          return null;
        });
    }))
      .then(function (items) {
        var imported = items.filter(function (item) { return item && item.content; });
        if (!imported.length && !validImportedMarkdownItems().length) {
          activeMarkdownPreviewIndex = null;
          refreshMergedMarkdownContent();
          setStatus("导入失败：未读取到有效 Markdown 内容", "error");
          return;
        }
        refreshMergedMarkdownContent();
        var titleBase = imported.length === 1
          ? imported[0].name
          : (imported[0] ? imported[0].name + " 等 " + imported.length + " 个知识图谱" : "知识图谱");
        if (imported.length && !$("#customRequirements").val().trim()) {
          $("#customRequirements").val("Title: " + titleBase.replace(/\.(md|markdown|zip|txt)$/i, ""));
        }
        var allImported = validImportedMarkdownItems();
        var totalChars = allImported.reduce(function (sum, item) {
          return sum + (item.charCount || (item.content || "").length);
        }, 0);
        setStatus("已累计导入 " + allImported.length + " 个 Markdown 知识图谱，共 " + totalChars + " 字符", "success");
      })
      .catch(function (err) {
        setStatus("导入请求失败: " + err.message, "error");
      })
      .finally(function () {
        $("#btnImportMarkdown").prop("disabled", false).text("导入 MD 知识图谱");
        $("#markdownImporter").val("");
      });
  });

  $("#supplementMarkdownImporter").on("change", function () {
    var files = Array.prototype.slice.call(this.files || []);
    if (!files.length) return;

    var markdownFiles = files.filter(function (file) {
      return /\.(md|markdown)$/i.test(file.name || "") ||
        /markdown/i.test(file.type || "");
    });
    if (!markdownFiles.length) {
      setStatus("请选择 .md 或 .markdown 补充章节文件", "error");
      $(this).val("");
      return;
    }

    $("#btnImportSupplementMarkdown").prop("disabled", true).text("导入中...");
    setStatus("正在识别补充章节目录...", "info");
    Promise.all(markdownFiles.map(function (file) {
      return new Promise(function (resolve, reject) {
        var reader = new FileReader();
        reader.onload = function () {
          resolve({
            fileName: markdownFileDisplayPath(file),
            content: String(reader.result || ""),
          });
        };
        reader.onerror = function () {
          reject(new Error("读取补充章节失败：" + (file.name || "未命名文件")));
        };
        reader.readAsText(file);
      });
    }))
      .then(function (items) {
        supplementChapterCatalog = [];
        items.forEach(function (item) {
          extractSupplementChapterCatalog(item.content, item.fileName).forEach(function (chapter) {
            chapter.id = "supplement-" + supplementChapterCatalog.length;
            chapter.expanded = false;
            supplementChapterCatalog.push(chapter);
          });
        });
        renderSupplementChapterPanel();
        if (supplementChapterCatalog.length) {
          setStatus("补充章节识别完成：共 " + supplementChapterCatalog.length + " 个，可勾选后添加", "success");
        } else {
          setStatus("未识别到 001 / 001.002 编号补充章节", "error");
        }
      })
      .catch(function (err) {
        setStatus(err.message || "读取补充章节失败", "error");
      })
      .finally(function () {
        $("#btnImportSupplementMarkdown").prop("disabled", false).text("导入补充章节");
        $("#supplementMarkdownImporter").val("");
      });
  });

  $("#markdownImportList").on("click", ".markdown-import-toggle", function (e) {
    e.preventDefault();
    var index = parseInt($(this).attr("data-markdown-index"), 10);
    toggleMarkdownImportItem(index);
  });

  $("#markdownImportList").on("click", ".markdown-import-remove", function (e) {
    e.preventDefault();
    e.stopPropagation();
    var index = parseInt($(this).attr("data-markdown-index"), 10);
    removeMarkdownImportItem(index);
  });

  $("#markdownImportList").on("click", ".markdown-section-toggle, .markdown-section-title", function (e) {
    e.preventDefault();
    e.stopPropagation();
    var fileIndex = parseInt($(this).attr("data-markdown-index"), 10);
    var sectionIndex = parseInt($(this).attr("data-section-index"), 10);
    previewMarkdownSection(fileIndex, sectionIndex);
  });

  $("#markdownImportList").on("click", ".markdown-section-quote", function (e) {
    e.preventDefault();
    e.stopPropagation();
    var fileIndex = parseInt($(this).attr("data-markdown-index"), 10);
    var sectionIndex = parseInt($(this).attr("data-section-index"), 10);
    toggleMarkdownSectionSelection(fileIndex, sectionIndex);
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

  $("#latexImporter").on("change", function () {
    var file = this.files && this.files[0];
    if (!file) return;
    if (/\.pdf$/i.test(file.name || "") || /pdf/i.test(file.type || "")) {
      setLatexImportLoading(true);
      loadPdfIntoEditablePpt(file, {
        chapterTitle: titleFromLatexFileName(file.name || ""),
      });
      setLatexImportLoading(false);
      $(this).val("");
      return;
    }
    if (/\.zip$/i.test(file.name || "") || /zip/i.test(file.type || "")) {
      setLatexImportLoading(true);
      loadOverleafZipIntoEditablePpt(file, {
        chapterTitle: titleFromLatexFileName(file.name || ""),
      }).always(function () {
        setLatexImportLoading(false);
        $("#latexImporter").val("");
      });
      return;
    }
    if (/\.(pptx|ppt)$/i.test(file.name || "") || /presentation|powerpoint/i.test(file.type || "")) {
      setLatexImportLoading(true);
      loadPptIntoLatexFromFile(file, {
        chapterTitle: titleFromLatexFileName(file.name || ""),
      }).always(function () {
        setLatexImportLoading(false);
        $("#latexImporter").val("");
      });
      return;
    }
    if (!/\.(tex|latex|txt)$/i.test(file.name || "") && !/tex|plain|text/i.test(file.type || "")) {
      setStatus("请选择 .tex / .pdf / .zip / .pptx / .ppt 文件", "error");
      $(this).val("");
      return;
    }
    importedLatexFileName = file.name || "";
    importedPdfFileName = "";
    setLatexImportLoading(true);
    setStatus("正在读取 LaTeX 文件...", "info");
    var reader = new FileReader();
    reader.onload = function () {
      var tex = String(reader.result || "");
      fullLatex = tex;
      sourceLatex = tex;
      updateLatexEditor(tex);
      $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf, #btnConvertPpt").prop("disabled", !tex.trim());
      updateLatexImportMeta("已导入：" + (importedLatexFileName || "LaTeX 文件"));
      loadLatexIntoEditablePpt(tex, {
        updateEditor: false,
        chapterTitle: titleFromLatexFileName(importedLatexFileName),
      });
    };
    reader.onerror = function () {
      setStatus("读取 LaTeX 文件失败", "error");
    };
    reader.onloadend = function () {
      setLatexImportLoading(false);
      $("#latexImporter").val("");
    };
    reader.readAsText(file);
  });

  $("#latexProjectImporter").on("change", function () {
    var files = Array.prototype.slice.call(this.files || []);
    if (!files.length) return;
    setLatexImportLoading(true);
    var request = loadLatexProjectIntoEditablePpt(files, {
      chapterTitle: titleFromLatexFileName((files.find(function (file) {
        return /\.(tex|latex)$/i.test(file.name || "") || /\.(tex|latex)$/i.test(file.webkitRelativePath || "");
      }) || {}).name || ""),
    });
    if (request && request.always) {
      request.always(function () {
        setLatexImportLoading(false);
        $("#latexProjectImporter").val("");
      });
    } else {
      setLatexImportLoading(false);
      $(this).val("");
    }
  });

  $("#equationSourceImporter").on("change", function () {
    var file = this.files && this.files[0];
    if (!file) return;
    if (!/\.(tex|latex|md|markdown|txt)$/i.test(file.name || "") && !/tex|markdown|plain|text/i.test(file.type || "")) {
      setStatus("请选择包含公式的 .tex / .md / .txt 章节文件", "error");
      $(this).val("");
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      resolveMissingEquationsFromSource(String(reader.result || ""), file.name || "");
    };
    reader.onerror = function () {
      setStatus("读取公式章节失败", "error");
      $("#equationSourceImporter").val("");
    };
    reader.readAsText(file);
  });
  document.addEventListener("wheel", containNestedWheelScroll, { passive: false, capture: true });

  editor.on("cursorActivity", scheduleLatexSelectionSync);
  editor.on("change", function () {
    scheduleLatexManualSync();
    if (!latexProgrammaticUpdate && !syncSelectionLock) {
      schedulePageChecklistUpdate(null, 260);
    }
  });
  editor.on("mousedown", clearLatexSyncSelectionOnEditorInput);
  editor.on("touchstart", clearLatexSyncSelectionOnEditorInput);
  var slideCanvasNode = document.getElementById("slideCanvas");
  if (slideCanvasNode) {
    slideCanvasNode.addEventListener("mousedown", clearPptSyncHighlightsOnEditorInput, true);
    slideCanvasNode.addEventListener("touchstart", clearPptSyncHighlightsOnEditorInput, true);
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function downloadFile(content, filename, mime) {
    var blob = content instanceof Blob
      ? content
      : (typeof content === "string")
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

  $("#btnTogglePageChecklist").on("click", function () {
    var currentLatex = editor && editor.getValue ? editor.getValue() : fullLatex;
    updatePageChecklist(currentLatex || "");
    $("#pageChecklistPanel").toggle();
  });

  $("#btnDownloadPageChecklist").on("click", function () {
    if (!pageChecklistText) return;
    downloadFile(pageChecklistText, "page_checklist_" + today() + ".txt", "text/plain");
  });

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
    slide.titleCredit = repairPptLatexArtifacts(slide.titleCredit || "");
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
    if (!Array.isArray(slide.formulaBoxes)) slide.formulaBoxes = [];
    slide.formulaBoxes.forEach(function (box) {
      if (box) box.formula = latexMathDisplaySource(box.formula || "");
    });
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

  function clearLatexSelectionTimer() {
    if (latexSelectionTimer) {
      clearTimeout(latexSelectionTimer);
      latexSelectionTimer = null;
    }
  }

  function clearLatexSyncSelectionOnEditorInput() {
    if (!latexSyncMarks.length) return;
    suppressLatexSelectionSyncUntil = Date.now() + 250;
    clearLatexSyncMarks();
    if (!editor || !editor.somethingSelected || !editor.somethingSelected()) return;
    runWithSyncSelectionLock(function () {
      var cursor = editor.getCursor ? editor.getCursor("head") : null;
      if (cursor && editor.setSelection) {
        editor.setSelection(cursor, cursor);
      } else if (cursor && editor.setCursor) {
        editor.setCursor(cursor);
      }
    });
  }

  function clearPptSyncHighlights() {
    $("#slideCanvas").find(".sync-highlight").removeClass("sync-highlight");
    if (pptSyncHighlightTimer) {
      clearTimeout(pptSyncHighlightTimer);
      pptSyncHighlightTimer = null;
    }
  }

  function clearPptSyncHighlightsOnEditorInput() {
    if (syncSelectionLock) return;
    if ($("#slideCanvas").find(".sync-highlight").length) {
      suppressPptSelectionSyncUntil = Date.now() + 250;
    }
    clearPptSyncHighlights();
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
      if (Date.now() < suppressPptSelectionSyncUntil) return;
      clearLatexSelectionTimer();
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
      var containingFrameKey = "";
      var containingFrameSize = Infinity;
      var bestContainingKey = "";
      var bestContainingSize = Infinity;
      Object.keys(latexSyncMap).forEach(function (key) {
        var range = latexSyncMap[key];
        if (!range) return;
        if (from < range.start || from > range.end) return;
        var size = Math.max(0, range.end - range.start);
        if (/:frame$/.test(key)) {
          if (size < containingFrameSize) {
            containingFrameSize = size;
            containingFrameKey = key;
          }
          return;
        }
        if (size < bestContainingSize) {
          bestContainingSize = size;
          bestContainingKey = key;
        }
      });
      return bestContainingKey || containingFrameKey;
    }
    var bestKey = "";
    var bestOverlap = 0;
    var bestSize = Infinity;
    var frameKey = "";
    var frameOverlap = 0;
    var frameSize = Infinity;
    Object.keys(latexSyncMap).forEach(function (key) {
      var range = latexSyncMap[key];
      if (!range) return;
      var overlap = Math.max(0, Math.min(to, range.end) - Math.max(from, range.start));
      if (!overlap) return;
      var size = Math.max(0, range.end - range.start);
      if (/:frame$/.test(key)) {
        if (overlap > frameOverlap || (overlap === frameOverlap && size < frameSize)) {
          frameOverlap = overlap;
          frameSize = size;
          frameKey = key;
        }
        return;
      }
      if (overlap > bestOverlap || (overlap === bestOverlap && size < bestSize)) {
        bestOverlap = overlap;
        bestSize = size;
        bestKey = key;
      }
    });
    return bestKey || frameKey;
  }

  function scheduleLatexSelectionSync() {
    if (syncSelectionLock || latexProgrammaticUpdate || suppressNextLatexManualSync) return;
    if (Date.now() < suppressLatexSelectionSyncUntil) return;
    if (latexSelectionTimer) clearTimeout(latexSelectionTimer);
    latexSelectionTimer = setTimeout(function () {
      latexSelectionTimer = null;
      if (syncSelectionLock || latexProgrammaticUpdate || suppressNextLatexManualSync) return;
      if (Date.now() < suppressLatexSelectionSyncUntil) return;
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
        columnSpec: "",
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
    return {
      headers: headers,
      rows: rows,
      headerRichHtml: table.headerRichHtml || [],
      rowRichHtml: table.rowRichHtml || [],
      columnSpec: table.columnSpec || "",
    };
  }

  function latexTableColumnWidths(columnSpec, count) {
    var widths = [];
    String(columnSpec || "").replace(/p\s*\{\s*([0-9.]+)\s*\\textwidth\s*\}/g, function (match, value) {
      widths.push(Math.max(4, Math.min(90, parseFloat(value) * 100)));
      return match;
    });
    if (widths.length !== count) return [];
    var total = widths.reduce(function (sum, value) { return sum + value; }, 0);
    if (!total) return [];
    return widths.map(function (value) {
      return (value / total * 100).toFixed(2) + "%";
    });
  }

  function normalizePlaceholders(placeholders) {
    return (placeholders || []).map(function (ph, idx) {
      ph = ph || {};
      var figure = extractFigureReference(ph.figure || ph.label || "");
      var key = normalizeFigureLabel(figure || ph.label || "");
      var figurePreview = key ? figurePreviewMap[key] : null;
      var width = clampNumber(ph.width, 80, 760, 270);
      var height = clampNumber(ph.height, 60, 380, 190);
      return {
        type: ph.type || "image",
        label: ph.label || figure || "图片占位",
        figure: figure,
        asset: ph.asset || ph.url || ph.path || (figurePreview && figurePreview.url) || pickPackageImageForFigure(figure || ph.label || "") || "",
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

  function ensureMissingEquationMacro(preamble, slides) {
    return preamble;
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

  function imagePathForLatex(img) {
    img = img || {};
    var imgPath = String(img.path || "").replace(/^\/+/, "");
    return imgPath;
  }

  function buildImageLatex(img, widthSpec) {
    var imgPath = imagePathForLatex(img);
    if (!imgPath) return "";
    return "  \\includegraphics[width=" + (widthSpec || "0.7\\textwidth") + "]{" + imgPath + "}";
  }

  function imageLatexForFrame(img, widthSpec) {
    var imgPath = imagePathForLatex(img);
    if (!imgPath) return "";
    var macro = String((img && img.latexMacro) || "").trim();
    if (/^safe(?:content|vertical|logo)image$/.test(macro)) {
      return "\\" + macro + "{" + imgPath + "}";
    }
    return "\\includegraphics[width=" + (widthSpec || "0.7\\textwidth") + "]{" + imgPath + "}";
  }

  function figureFrameTitle(slide, img, fallback) {
    slide = slide || {};
    var title = String(slide.title || "").trim();
    if (/^figure\s+\d+(?:\.\d+)?/i.test(title)) return title;
    var imgPath = imagePathForLatex(img || {});
    var match = imgPath.match(/(?:^|\/)(\d+(?:\.\d+)*)\.(?:png|jpe?g|pdf|eps|svg)$/i);
    if (match) return "Figure " + match[1];
    return title || fallback || "图片";
  }

  function isPortraitImage(img) {
    img = img || {};
    var w = parseFloat(img.naturalWidth || img.width || 0);
    var h = parseFloat(img.naturalHeight || img.height || 0);
    return h > w && w > 0;
  }

  function imageCaptionText(slide) {
    slide = slide || {};
    var parts = [];
    (slide.items || []).forEach(function (item) {
      if (item) parts.push(item);
    });
    if (slide.notes) parts.push(slide.notes);
    return repairPptLatexArtifacts(parts.join(" "));
  }

  function buildTopImageBottomTextLatex(slide) {
    slide = slide || {};
    var img = (slide.images && slide.images[0]) || null;
    var imgPath = imagePathForLatex(img);
    if (!imgPath) return "";
    var caption = imageCaptionText(slide) || slide.subtitle || slide.title || "图片说明待补充。";
    var out = [];
    if (isPortraitImage(img)) {
      out.push("\\begin{frame}{" + richHtmlToLatex("", figureFrameTitle(slide, img, "图片")) + "}");
      out.push("  \\begin{columns}[T]");
      out.push("    \\begin{column}{0.45\\textwidth}");
      out.push("      \\scriptsize " + richHtmlToLatex("", caption));
      out.push("    \\end{column}");
      out.push("    \\begin{column}{0.45\\textwidth}");
      out.push("      \\centering");
      out.push("      " + imageLatexForFrame(img, "\\textwidth"));
      out.push("    \\end{column}");
      out.push("  \\end{columns}");
      out.push("\\end{frame}");
      return out.join("\n");
    }
    out.push("\\begin{frame}{" + richHtmlToLatex("", figureFrameTitle(slide, img, "图片")) + "}");
    out.push("  \\centering");
    out.push("  " + imageLatexForFrame(img, "0.7\\textwidth"));
    out.push("  \\vspace{0.3cm}");
    out.push("  \\begin{center}");
    out.push("    \\parbox{0.95\\textwidth}{\\scriptsize " + richHtmlToLatex("", caption) + "}");
    out.push("  \\end{center}");
    out.push("\\end{frame}");
    return out.join("\n");
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
      var itemText = String(items[i] || "").replace(/\s*\[\d+\.\]\s*$/, "");
      out.push(
        "        \\item \\textcolor{black}{" + escapeLatexTextPreservingMath(itemText) + "}"
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
      var prefix = "        \\item \\textcolor{black}{";
      var itemText = String(items[i] || "").replace(/\s*\[\d+\.\]\s*$/, "");
      addTrackedLine(prefix, itemText, "}", syncKey(slideIdx, "item", i));
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
    if (slide && slide.images && slide.images.length) {
      return buildTopImageBottomTextLatex(slide);
    }
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
        if (tb.type === "formula") continue;
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

    if (slide.formulaBoxes && slide.formulaBoxes.length) {
      for (var fb = 0; fb < slide.formulaBoxes.length; fb++) {
        var formulaBox = slide.formulaBoxes[fb] || {};
        var formula = latexMathDisplaySource(formulaBox.formula || "");
        if (!formula) continue;
        out.push("  \\begin{center}");
        out.push("    \\[" + formula + "\\]");
        out.push("  \\end{center}");
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

    function addTrackedLatexLine(prefix, latexText, suffix, key) {
      var content = latexText || "";
      var lineMap = {};
      lineMap[key] = {
        start: prefix.length,
        end: prefix.length + content.length,
        slideIdx: slideIdx,
      };
      addLine(prefix + content + (suffix || ""), lineMap);
    }

    if (slide && slide.images && slide.images.length) {
      var topImg = slide.images[0] || {};
      var topImgPath = imagePathForLatex(topImg);
      if (topImgPath) {
        var topCaption = imageCaptionText(slide) || slide.subtitle || slide.title || "图片说明待补充。";
        if (isPortraitImage(topImg)) {
          addLine("\\begin{frame}{" + richHtmlToLatex("", figureFrameTitle(slide, topImg, "图片")) + "}");
          addLine("  \\begin{columns}[T]");
          addLine("    \\begin{column}{0.45\\textwidth}");
          addLine("      \\centering");
          addLine("      " + imageLatexForFrame(topImg, "\\textwidth"));
          addLine("    \\end{column}");
          addLine("    \\begin{column}{0.45\\textwidth}");
          addTrackedLine("      \\scriptsize ", topCaption, "", syncKey(slideIdx, "notes"));
          addLine("    \\end{column}");
          addLine("  \\end{columns}");
          addLine("\\end{frame}");
          Object.assign(map, localMap);
          return out.join("\n");
        }
        addLine("\\begin{frame}{" + richHtmlToLatex("", figureFrameTitle(slide, topImg, "图片")) + "}");
        addLine("  \\centering");
        addLine("  " + imageLatexForFrame(topImg, "0.7\\textwidth"));
        addLine("  \\vspace{0.3cm}");
        addLine("  \\begin{center}");
        addTrackedLine("    \\parbox{0.95\\textwidth}{\\scriptsize ", topCaption, "}", syncKey(slideIdx, "notes"));
        addLine("  \\end{center}");
        addLine("\\end{frame}");
        Object.assign(map, localMap);
        return out.join("\n");
      }
    }

    if (slide.titleRichHtml) {
      addTrackedLatexLine("\\begin{frame}{", richHtmlToLatex(slide.titleRichHtml, slide.title || ""), "}", syncKey(slideIdx, "title"));
    } else {
      addTrackedLine("\\begin{frame}{", slide.title || "", "}", syncKey(slideIdx, "title"));
    }

    if (slide.subtitle) {
      if (slide.subtitleRichHtml) {
        addTrackedLatexLine("  \\textit{", richHtmlToLatex(slide.subtitleRichHtml, slide.subtitle), "}", syncKey(slideIdx, "subtitle"));
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
          addTrackedLatexLine("    \\item ", richHtmlToLatex(itemRich, slide.items[i] || ""), "", syncKey(slideIdx, "item", i));
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
        if (tb.type === "formula") continue;
        var tbPrefix = "    \\fbox{\\parbox{0.92\\linewidth}{";
        var tbSuffix = "}}";
        if (tb.fontSize) {
          tbPrefix += "{\\fontsize{" + tb.fontSize + "}{" + Math.round(tb.fontSize * 1.2) + "}\\selectfont ";
          tbSuffix += "}";
        }
        addLine("  \\begin{center}");
        if (tb.richHtml) {
          addTrackedLatexLine(tbPrefix, richHtmlToLatex(tb.richHtml, tb.text), tbSuffix, syncKey(slideIdx, "textbox", k));
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

    if (slide.formulaBoxes && slide.formulaBoxes.length) {
      for (var fb = 0; fb < slide.formulaBoxes.length; fb++) {
        var formulaBox = slide.formulaBoxes[fb] || {};
        var formula = latexMathDisplaySource(formulaBox.formula || "");
        if (!formula) continue;
        addLine("  \\begin{center}");
        var formulaLine = "    \\[" + formula + "\\]";
        addLine(formulaLine, (function () {
          var m = {};
          m[syncKey(slideIdx, "formulaBox", fb)] = {
            start: 6,
            end: Math.max(6, formulaLine.length - 2),
            slideIdx: slideIdx,
          };
          return m;
        })());
        addLine("  \\end{center}");
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
    preamble = ensureMissingEquationMacro(preamble, data.slides || []);
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
    schedulePageChecklistUpdate(tex || "", 160);
  }

  function rebuildRenderedPageLocationMap(data, tex) {
    var map = {};
    var source = String(tex || "");
    if (!data || !Array.isArray(data.slides) || !source) {
      latexSyncMap = map;
      return;
    }
    var frames = [];
    var frameRe = /\\begin\{frame\}[\s\S]*?\\end\{frame\}/g;
    var match;
    while ((match = frameRe.exec(source)) !== null) {
      frames.push({ start: match.index, end: frameRe.lastIndex });
    }
    for (var i = 0; i < data.slides.length && i < frames.length; i++) {
      map[syncKey(i, "frame")] = { start: frames[i].start, end: frames[i].end, slideIdx: i };
    }
    latexSyncMap = map;
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

    function addCandidate(candidates, value) {
      value = String(value || "").trim();
      if (!value) return;
      if (candidates.indexOf(value) === -1) candidates.push(value);
    }

    function latexTextCandidates(rawText, richHtml) {
      var candidates = [];
      if (richHtml) addCandidate(candidates, richHtmlToLatex(richHtml, rawText || ""));
      addCandidate(candidates, escapeLatexTextPreservingMath(rawText || ""));
      addCandidate(candidates, escapeLatexText(rawText || ""));
      addCandidate(candidates, rawText || "");
      return candidates;
    }

    function addRangeByText(frame, key, slideIdx, rawText, richHtml) {
      if (map[key]) return;
      var candidates = latexTextCandidates(rawText, richHtml);
      for (var c = 0; c < candidates.length; c++) {
        var idx = source.indexOf(candidates[c], frame.start);
        if (idx !== -1 && idx + candidates[c].length <= frame.end) {
          addRange(key, idx, idx + candidates[c].length, slideIdx);
          return;
        }
      }
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

      addRangeByText(frame, syncKey(i, "subtitle"), i, slide.subtitle || "", slide.subtitleRichHtml || "");
      if (slide.table && slide.table.headers) {
        var table = normalizeTable(slide.table);
        (table.headers || []).forEach(function (header, h) {
          addRangeByText(frame, syncKey(i, "th", h), i, header || "", (table.headerRichHtml || [])[h] || "");
        });
        (table.rows || []).forEach(function (row, r) {
          (row || []).forEach(function (cell, c) {
            addRangeByText(frame, syncKey(i, "td", r, c), i, cell || "", ((table.rowRichHtml || [])[r] || [])[c] || "");
          });
        });
      }
      (slide.textboxes || []).forEach(function (tb, tbIdx) {
        addRangeByText(frame, syncKey(i, "textbox", tbIdx), i, (tb && tb.text) || "", (tb && tb.richHtml) || "");
      });
      (slide.callouts || []).forEach(function (callout, calloutIdx) {
        addRangeByText(frame, syncKey(i, "callout", calloutIdx), i, (callout && callout.text) || "", "");
      });
    }

    latexSyncMap = map;
  }

  function parseLatexIntoPptFromEditor() {
    var tex = editor.getValue ? editor.getValue() : fullLatex;
    fullLatex = tex || "";
    sourceLatex = fullLatex;
    $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf, #btnConvertPpt").prop("disabled", !fullLatex);
    updateDownloadPptxButton();
    if (isLatexImportMode) return;
    if (!fullLatex.trim()) return;

    var seq = ++latexManualSyncSeq;
    $.ajax({
      url: "/beamer-generator/api/parse-slides",
      method: "POST",
      contentType: "application/json",
      data: JSON.stringify({ latex: fullLatex }),
      success: function (data) {
        if (seq !== latexManualSyncSeq || !data || data.error || !data.slides) return;
        if (data.latex && data.latex !== fullLatex) {
          fullLatex = data.latex;
          sourceLatex = fullLatex;
          updateLatexEditor(fullLatex);
        }
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
    if (isLatexImportMode) return;
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
    if (isLatexImportMode || hasRenderedLatexPages(slidesData)) {
      latexManualSyncSeq += 1;
      var keepSlideIdxRendered = currentSlideIdx;
      currentSlideIdx = keepSlideIdxRendered;
      renderSlideList();
      if (currentSlideIdx >= 0) {
        $(".slide-thumb").removeClass("active").eq(currentSlideIdx).addClass("active");
      }
      return;
    }
    latexManualSyncSeq += 1;
    var keepSlideIdx = currentSlideIdx;
    syncTitleMetaFromSlides();
    ensureAllSlideFigurePlaceholders(slidesData);
    fullLatex = buildLatexFromSlides(slidesData);
    if (!isLatexImportMode) {
      fullLatex = applyCustomRequirementOverrides(fullLatex, currentCustomRequirements);
    }
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
    if (isLatexImportMode || hasRenderedLatexPages(slidesData)) return;
    if (latexSyncTimer) clearTimeout(latexSyncTimer);
    latexSyncTimer = setTimeout(function () {
      latexSyncTimer = null;
      syncCurrentSlideToLatex();
    }, 120);
  }

  function applyInputCollapsedState() {
    $(".container").toggleClass("input-collapsed", inputCollapsed);
    if (!inputCollapsed) $(".container").removeClass("outline-only");
    $(".panel-input").prop("hidden", inputCollapsed);
    $("#btnToggleInputPanel")
      .text(inputCollapsed ? ">>" : "<<")
      .attr("aria-label", inputCollapsed ? "Expand left panel" : "Collapse left panel")
      .attr("title", inputCollapsed ? "Expand left panel" : "Collapse left panel");
    $("#innerResizeHandle").toggle(inputCollapsed);

    if (inputCollapsed) {
      setActiveTab(activeTab || "latex");
    } else {
      $(".panel-output").css("grid-template-columns", "");
      setActiveTab(activeTab || "latex");
    }

    refreshEditorSize();
  }

  function setActiveTab(tab) {
    if (tab !== "latex" && tab !== "outline" && tab !== "ppt") tab = "latex";
    activeTab = tab;
    $(".tab-btn").removeClass("active");
    $('.tab-btn[data-tab="' + tab + '"]').addClass("active");
    if (inputCollapsed) {
      if (tab === "outline") {
        $(".container").addClass("outline-only");
        $(".panel-output").css("grid-template-columns", "1fr");
        $("#viewOutline").addClass("active").show();
        $("#viewLatex, #viewPpt").removeClass("active").hide();
        $("#innerResizeHandle").hide();
        $(".latex-actions, .ppt-actions").hide();
      } else {
        $(".container").removeClass("outline-only");
        $("#viewLatex, #viewPpt").addClass("active").show();
        $("#viewOutline").removeClass("active").hide();
        $("#innerResizeHandle").show();
        $(".latex-actions, .ppt-actions").show();
        if (collapsedPaneResize) {
          collapsedPaneResize.applySplit(latexPptSplitRatio);
        }
      }
      refreshEditorSize();
      return;
    }
    if (tab === "latex") {
      $("#viewLatex").addClass("active").show();
      $("#viewOutline").removeClass("active").hide();
      $("#viewPpt").removeClass("active").hide();
      $(".latex-actions").show();
      $(".ppt-actions").hide();
    } else if (tab === "outline") {
      $("#viewOutline").addClass("active").show();
      $("#viewLatex").removeClass("active").hide();
      $("#viewPpt").removeClass("active").hide();
      $(".latex-actions, .ppt-actions").hide();
    } else {
      $("#viewPpt").addClass("active").show();
      $("#viewLatex").removeClass("active").hide();
      $("#viewOutline").removeClass("active").hide();
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

  function htmlEscape(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function uniqueList(items) {
    var seen = {};
    var result = [];
    (items || []).forEach(function (item) {
      var text = String(item || "").trim();
      if (!text || seen[text]) return;
      seen[text] = true;
      result.push(text);
    });
    return result;
  }

  function extractLatexFramesForChecklist(latex) {
    var frames = [];
    var re = /\\begin\{frame\}(?:\[[^\]]*\])?(?:\{([^}]*)\})?([\s\S]*?)\\end\{frame\}/g;
    var match;
    while ((match = re.exec(latex || "")) !== null) {
      var body = match[2] || "";
      var title = String(match[1] || "").trim();
      if (!title) {
        var titleMatch = /\\frametitle\{([^}]*)\}/.exec(body);
        title = titleMatch ? titleMatch[1].trim() : "";
      }
      frames.push({ title: title || ("Frame " + (frames.length + 1)), body: body });
    }
    return frames;
  }

  function outlineSectionIdsByPage(outline) {
    var ids = [];
    ((outline && outline.sections) || []).forEach(function (section) {
      var count = ((section.frames || []).length) || section.slide_count || 0;
      for (var i = 0; i < count; i++) ids.push(section.id || "");
    });
    return ids;
  }

  function extractFormulaLabelsForChecklist(text) {
    var items = [];
    var patterns = [
      /Equation\s*\(?(\d+(?:\.\d+)+)\)?/gi,
      /Eq\.?\s*\(?(\d+(?:\.\d+)+)\)?/gi,
      /\\tag\{([^}]+)\}/g,
      /\\label\{([^}]*(?:eq|equation)[^}]*)\}/gi,
      /\\eqref\{([^}]+)\}/g,
      /\\kgmissingequation\{num:([^}]+)\}/g,
      /\\kgmissingequation\{label:([^}]+)\}/g,
    ];
    patterns.forEach(function (pattern) {
      var match;
      while ((match = pattern.exec(text || "")) !== null) {
        items.push(match[1]);
      }
    });
    return uniqueList(items);
  }

  function extractImageNumbersForChecklist(text) {
    var items = [];
    var patterns = [
      /Figure\s*(\d+(?:\.\d+)+)/gi,
      /Fig\.?\s*(\d+(?:\.\d+)+)/gi,
      /图\s*(\d+(?:[._]\d+)+)/g,
      /fig\/(?:图)?(\d+(?:[._]\d+)+)[^}\s]*/gi,
      /figures\/(?:图)?(\d+(?:[._]\d+)+)[^}\s]*/gi,
    ];
    patterns.forEach(function (pattern) {
      var match;
      while ((match = pattern.exec(text || "")) !== null) {
        items.push(String(match[1] || "").replace(/_/g, "."));
      }
    });
    return uniqueList(items.map(function (item) {
      return item.indexOf("Figure ") === 0 ? item : "Figure " + item;
    }));
  }

  function buildPageChecklistText(latex, outline) {
    var frames = extractLatexFramesForChecklist(latex);
    var sectionIds = outlineSectionIdsByPage(outline);
    if (!frames.length) return "";
    return frames.map(function (frame, index) {
      var formulas = extractFormulaLabelsForChecklist(frame.body);
      var images = extractImageNumbersForChecklist(frame.title + "\n" + frame.body);
      return [
        "Page " + (index + 1) + ": " + frame.title,
        "大节标号: " + (sectionIds[index] || "未识别"),
        "公式标号: " + (formulas.length ? formulas.join(", ") : "无"),
        "图片编号: " + (images.length ? images.join(", ") : "无"),
      ].join("\n");
    }).join("\n\n");
  }

  function updatePageChecklist(latex) {
    var source = latex || "";
    pageChecklistText = buildPageChecklistText(source, generatedOutline);
    $("#pageChecklistText").text(pageChecklistText || "暂无逐页清单。");
    var hasLatex = !!String(source || fullLatex || "").trim();
    $("#btnTogglePageChecklist")
      .prop("disabled", !hasLatex)
      .text(pageChecklistText ? "逐页清单" : "逐页清单");
    $("#btnDownloadPageChecklist").prop("disabled", !pageChecklistText);
  }

  function schedulePageChecklistUpdate(latex, delayMs) {
    var source = typeof latex === "string"
      ? latex
      : (editor && editor.getValue ? editor.getValue() : fullLatex);
    if (pageChecklistTimer) clearTimeout(pageChecklistTimer);
    pageChecklistTimer = setTimeout(function () {
      pageChecklistTimer = null;
      updatePageChecklist(source || "");
    }, typeof delayMs === "number" ? delayMs : 160);
  }

  function readGptConfig() {
    var apiKey = String($("#gptApiKey").val() || "").trim();
    var apiBase = String($("#gptApiBase").val() || "").trim();
    var model = String($("#gptModel").val() || "").trim();
    if (!apiKey) {
      setStatus("请输入本次生成使用的 GPT API Key", "error");
      $("#gptApiKey").focus();
      return null;
    }
    if (!apiBase) {
      setStatus("请输入 GPT API Base URL", "error");
      $("#gptApiBase").focus();
      return null;
    }
    if (!model) {
      setStatus("请输入 GPT 模型名称", "error");
      $("#gptModel").focus();
      return null;
    }
    activeGptConfig = { api_key: apiKey, base_url: apiBase, model: model };
    return activeGptConfig;
  }

  function saveGptConfigToBrowser(config) {
    localStorage.setItem(GPT_CONFIG_STORAGE_KEY, JSON.stringify({
      api_key: config.api_key,
      base_url: config.base_url,
      model: config.model,
    }));
  }

  function restoreGptConfigFromBrowser() {
    try {
      var raw = localStorage.getItem(GPT_CONFIG_STORAGE_KEY);
      if (!raw) return;
      var config = JSON.parse(raw);
      if (config.api_key) $("#gptApiKey").val(config.api_key);
      if (config.base_url) $("#gptApiBase").val(config.base_url);
      if (config.model) $("#gptModel").val(config.model);
      activeGptConfig = {
        api_key: String(config.api_key || "").trim(),
        base_url: String(config.base_url || "").trim(),
        model: String(config.model || "").trim(),
      };
    } catch (err) {
      localStorage.removeItem(GPT_CONFIG_STORAGE_KEY);
    }
  }

  function outlineStorageTitle(outline) {
    outline = outline || generatedOutline || {};
    var base = String(outline.title || $("#customRequirements").val() || "saved_outline").trim();
    base = base.replace(/^Title:\s*/i, "").replace(/[\\/:*?"<>|]+/g, "_").replace(/\s+/g, "_");
    return base || "saved_outline";
  }

  function saveOutlineToBrowser(outline) {
    localStorage.setItem(OUTLINE_STORAGE_KEY, JSON.stringify({
      saved_at: new Date().toISOString(),
      outline: outline,
    }));
  }

  function loadOutlineFromBrowser() {
    var raw = localStorage.getItem(OUTLINE_STORAGE_KEY);
    if (!raw) return null;
    var data = JSON.parse(raw);
    return data && data.outline ? data.outline : null;
  }

  function selectedSectionsPayload() {
    return getSelectedMarkdownSections().map(function (section) {
      return {
        file: section.fileTitle,
        title: section.title,
        id: section.id,
      };
    });
  }

  function applySelectedSectionsRequirement(requirements, selectedSections) {
    var result = String(requirements || "").trim();
    if (!selectedSections.length) return result;
    var selectionRequirement = "本次只根据已引用的 Markdown 小节生成 PPT，不要使用未引用小节。已引用小节：" +
      selectedSections.map(function (section) {
        return section.file + " / " + section.title;
      }).join("；");
    return result ? result + "\n" + selectionRequirement : selectionRequirement;
  }

  function normalizeNumericText(value) {
    return String(value || "").replace(/[０-９]/g, function (char) {
      return String(char.charCodeAt(0) - 0xff10);
    });
  }

  function readClampedInt(selector, fallback, minValue, maxValue) {
    var raw = normalizeNumericText($(selector).val());
    var match = raw.match(/\d+/);
    var value = match ? parseInt(match[0], 10) : fallback;
    if (Number.isNaN(value)) value = fallback;
    value = Math.max(minValue, Math.min(maxValue, value));
    $(selector).val(String(value));
    return value;
  }

  function readSectionSlideRange() {
    var minSlides = readClampedInt("#sectionSlideMin", 1, 1, 80);
    var maxSlides = readClampedInt("#sectionSlideMax", 8, 1, 80);
    if (maxSlides < minSlides) {
      maxSlides = minSlides;
      $("#sectionSlideMax").val(String(maxSlides));
    }
    return { min: minSlides, max: maxSlides };
  }

  $("#sectionSlideMin, #sectionSlideMax").on("input", function () {
    var cleaned = normalizeNumericText($(this).val()).replace(/[^\d]/g, "");
    if ($(this).val() !== cleaned) $(this).val(cleaned);
  }).on("blur", function () {
    readSectionSlideRange();
  });

  function buildBaseGenerationPayload(content) {
    var config = readGptConfig();
    if (!config) return null;
    var selectedSections = selectedSectionsPayload();
    var sectionSlideRange = readSectionSlideRange();
    currentCustomRequirements = applySelectedSectionsRequirement(
      $("#customRequirements").val().trim(),
      selectedSections
    );
    return {
      provider: "gpt",
      content: content,
      api_key: config.api_key,
      base_url: config.base_url,
      style: $("#style").val(),
      custom_requirements: currentCustomRequirements,
      slide_count: Math.max(1, Math.min(80, parseInt($("#slideCount").val(), 10) || 7)),
      section_slide_min: sectionSlideRange.min,
      section_slide_max: sectionSlideRange.max,
      language: $("#language").val(),
      model: config.model,
      figure_assets: buildFigureAssetPayload(),
      selected_sections: selectedSections,
    };
  }

  $("#btnApplyGptConfig").on("click", function () {
    var config = readGptConfig();
    if (!config) return;
    setStatus("GPT API 配置已提交，本次生成将使用该配置。", "success");
  });

  $("#btnSaveGptConfig").on("click", function () {
    var config = readGptConfig();
    if (!config) return;
    saveGptConfigToBrowser(config);
    setStatus("GPT API 配置已保存到本机浏览器。", "success");
  });

  function updateOutlineSummary() {
    if (!generatedOutline || !generatedOutline.sections) {
      $("#outlineSummary").text("");
      return;
    }
    var sectionCount = generatedOutline.sections.length;
    var frameCount = generatedOutline.sections.reduce(function (sum, section) {
      return sum + ((section.frames && section.frames.length) || 0);
    }, 0);
    $("#outlineSummary").text(sectionCount + " 个大节，" + frameCount + " 个 frame");
  }

  function normalizeOutlineFrameCounts(outline) {
    outline = outline || { title: "Presentation", target_slide_count: 0, sections: [] };
    outline.sections = Array.isArray(outline.sections) ? outline.sections : [];
    outline.target_slide_count = 0;
    outline.sections.forEach(function (section) {
      section.frames = Array.isArray(section.frames) ? section.frames : [];
      section.slide_count = section.frames.length;
      outline.target_slide_count += section.frames.length;
    });
    return outline;
  }

  function requireRenderableOutline(outline) {
    var normalized = normalizeOutlineFrameCounts(outline);
    if (!normalized.sections.length) {
      throw new Error("后端返回的纪要为空，没有可展示的大节");
    }
    var frameCount = normalized.sections.reduce(function (sum, section) {
      return sum + ((section.frames && section.frames.length) || 0);
    }, 0);
    if (!frameCount) {
      throw new Error("后端返回的纪要没有 frame 页面");
    }
    return normalized;
  }

  function refreshOutlineMathPreviews($scope) {
    var $root = $scope && $scope.length ? $scope : $("#outlineEditor");
    $root.find(".outline-section").each(function () {
      var $section = $(this);
      renderMathText(
        $section.find(".outline-section-summary-preview").first(),
        $section.find(".outline-section-summary").val() || "",
        { emptyText: "暂无大节概要预览。" }
      );
    });
    $root.find(".outline-frame").each(function () {
      var $frame = $(this);
      renderMathText(
        $frame.find(".outline-frame-points-preview").first(),
        $frame.find(".outline-frame-points").val() || "",
        { emptyText: "暂无要点预览。" }
      );
    });
  }

  function renderOutlineEditor(outline) {
    generatedOutline = normalizeOutlineFrameCounts(outline);
    var sections = generatedOutline.sections || [];
    if (!sections.length) {
      $("#outlineEditor").html("");
      $("#outlinePanel").hide();
      $("#outlinePlaceholder").show();
      updateOutlineSummary();
      schedulePageChecklistUpdate(fullLatex, 0);
      return;
    }
    activeOutlineSectionIndex = Math.max(0, Math.min(activeOutlineSectionIndex, sections.length - 1));
    var activeSection = sections[activeOutlineSectionIndex] || {};
    var html = "";
    html += '<div class="outline-workspace">';
    html += '<div class="outline-section-nav" aria-label="纪要大节目录">';
    var pageOffset = 0;
    sections.forEach(function (section, sectionIndex) {
      var frameCount = (section.frames || []).length;
      html += '<div class="outline-section-nav-item' + (sectionIndex === activeOutlineSectionIndex ? " active" : "") + '" data-section="' + sectionIndex + '" role="button" tabindex="0">';
      html += '<span class="outline-section-nav-id">' + htmlEscape(section.id || String(sectionIndex + 1).padStart(3, "0")) + '</span>';
      html += '<span class="outline-section-nav-title">' + htmlEscape(section.title || ("大节 " + (sectionIndex + 1))) + '</span>';
      html += '<span class="outline-section-nav-count">' + frameCount + ' 页</span>';
      html += '<div class="outline-page-index-popover" aria-label="本大节页面索引">';
      html += '<div class="outline-page-index-title">页面索引</div>';
      if (!frameCount) {
        html += '<div class="outline-page-index-empty">暂无页面</div>';
      }
      (section.frames || []).forEach(function (frame, frameIndex) {
        var pageNumber = pageOffset + frameIndex + 1;
        html += '<button type="button" class="outline-page-index-item" data-section="' + sectionIndex + '" data-frame="' + frameIndex + '">';
        html += '<span class="outline-page-index-number">P' + pageNumber + '</span>';
        html += '<span class="outline-page-index-text">' + htmlEscape(frame.title || ("Frame " + (frameIndex + 1))) + '</span>';
        html += '</button>';
      });
      html += '</div>';
      html += '</div>';
      pageOffset += frameCount;
    });
    html += '</div>';
    html += '<div class="outline-section-detail">';
    html += '<div class="outline-section" data-section="' + activeOutlineSectionIndex + '">';
    html += '<div class="outline-section-head">';
    html += '<input class="outline-section-id" value="' + htmlEscape(activeSection.id || "") + '" placeholder="001" />';
    html += '<input class="outline-section-title" value="' + htmlEscape(activeSection.title || "") + '" placeholder="大节标题" />';
    html += '<input class="outline-section-count" type="number" min="1" value="' + ((activeSection.frames || []).length) + '" title="大节页数" />';
    html += '<button type="button" class="btn-secondary outline-refresh-section">刷新本节</button>';
    html += '<button type="button" class="btn-secondary outline-add-frame">新增 frame</button>';
    html += '<button type="button" class="btn-secondary outline-save-section">保存本节</button>';
    html += '</div>';
    html += '<textarea class="outline-section-summary" placeholder="大节内容概要">' + htmlEscape(activeSection.summary || "") + '</textarea>';
    html += '<div class="outline-math-preview-label">大节概要公式预览</div>';
    html += '<div class="outline-math-preview outline-section-summary-preview"></div>';
    html += '<div class="outline-frames">';
    (activeSection.frames || []).forEach(function (frame, frameIndex) {
      html += '<div class="outline-frame" data-frame="' + frameIndex + '" id="outline-frame-' + activeOutlineSectionIndex + '-' + frameIndex + '">';
      html += '<div class="outline-frame-head">';
      html += '<input class="outline-frame-title" value="' + htmlEscape(frame.title || "") + '" placeholder="frame 主题" />';
      html += '<button type="button" class="btn-secondary outline-remove-frame">删除</button>';
      html += '</div>';
      html += '<textarea class="outline-frame-summary" placeholder="本页内容概要">' + htmlEscape(frame.summary || "") + '</textarea>';
      html += '<textarea class="outline-frame-points" placeholder="每行一个要点">' + htmlEscape((frame.key_points || []).join("\n")) + '</textarea>';
      html += '<div class="outline-math-preview-label">本页要点公式预览</div>';
      html += '<div class="outline-math-preview outline-frame-points-preview"></div>';
      html += '</div>';
    });
    html += '</div>';
    html += '<div class="outline-section-tools">';
    html += '<button type="button" class="btn-secondary outline-add-frame">新增 frame</button>';
    html += '<button type="button" class="btn-secondary outline-remove-section">删除大节</button>';
    html += '</div>';
    html += '</div>';
    html += '</div>';
    html += '</div>';
    $("#outlineEditor").html(html);
    $("#outlinePanel").show();
    $("#outlinePlaceholder").hide();
    $("#tabOutline").prop("disabled", false);
    setActiveTab("outline");
    updateOutlineSummary();
    refreshOutlineMathPreviews($("#outlineEditor"));
    schedulePageChecklistUpdate(fullLatex, 0);
  }

  function collectOutlineFromEditor() {
    var outline = {
      title: (generatedOutline && generatedOutline.title) || "Presentation",
      target_slide_count: 0,
      sections: (generatedOutline && generatedOutline.sections ? generatedOutline.sections : []).map(function (section) {
        return {
          id: section.id || "",
          title: section.title || "",
          summary: section.summary || "",
          slide_count: section.slide_count || ((section.frames || []).length),
          frames: (section.frames || []).map(function (frame) {
            return {
              title: frame.title || "",
              summary: frame.summary || "",
              key_points: (frame.key_points || []).slice(),
            };
          }),
        };
      }),
    };
    $("#outlineEditor .outline-section").each(function () {
      var $section = $(this);
      var sectionIndex = parseInt($section.data("section"), 10);
      var frames = [];
      $section.find(".outline-frame").each(function () {
        var $frame = $(this);
        var points = String($frame.find(".outline-frame-points").val() || "")
          .split(/\r?\n/)
          .map(function (line) { return line.trim(); })
          .filter(Boolean);
        frames.push({
          title: String($frame.find(".outline-frame-title").val() || "").trim(),
          summary: String($frame.find(".outline-frame-summary").val() || "").trim(),
          key_points: points,
        });
      });
      if (Number.isNaN(sectionIndex)) sectionIndex = outline.sections.length;
      outline.sections[sectionIndex] = {
        id: String($section.find(".outline-section-id").val() || "").trim(),
        title: String($section.find(".outline-section-title").val() || "").trim(),
        summary: String($section.find(".outline-section-summary").val() || "").trim(),
        slide_count: frames.length,
        frames: frames,
      };
    });
    outline.sections.forEach(function (section) {
      outline.target_slide_count += ((section.frames && section.frames.length) || 0);
    });
    return outline;
  }

  $("#btnAddOutlineSection").on("click", function () {
    var outline = collectOutlineFromEditor();
    var nextIndex = outline.sections.length + 1;
    outline.sections.push({
      id: String(nextIndex).padStart(3, "0"),
      title: "New Section",
      summary: "",
      slide_count: 1,
      frames: [{ title: "New Frame", summary: "", key_points: [] }],
    });
    activeOutlineSectionIndex = outline.sections.length - 1;
    renderOutlineEditor(outline);
  });

  $("#btnSaveOutline").on("click", function () {
    if (!generatedOutline || !generatedOutline.sections || !generatedOutline.sections.length) {
      setStatus("当前没有可保存的纪要。", "error");
      return;
    }
    var outline = collectOutlineFromEditor();
    saveOutlineToBrowser(outline);
    generatedOutline = outline;
    updateOutlineSummary();
    setStatus("纪要已保存到本机浏览器。", "success");
  });

  $("#btnLoadSavedOutline").on("click", function () {
    loadSavedOutlineIntoEditor();
  });

  $("#btnLoadSavedOutlineInput").on("click", function () {
    loadSavedOutlineIntoEditor();
  });

  function loadSavedOutlineIntoEditor() {
    try {
      var outline = loadOutlineFromBrowser();
      if (!outline) {
        setStatus("本机浏览器中没有已保存纪要。", "error");
        return;
      }
      activeOutlineSectionIndex = 0;
      renderOutlineEditor(requireRenderableOutline(outline));
      setStatus("已调用保存的纪要，可继续编辑或生成 LaTeX。", "success");
    } catch (err) {
      setStatus("调用纪要失败: " + err.message, "error");
    }
  }

  $("#btnDownloadOutline").on("click", function () {
    if (!generatedOutline || !generatedOutline.sections || !generatedOutline.sections.length) {
      setStatus("当前没有可下载的纪要。", "error");
      return;
    }
    var outline = collectOutlineFromEditor();
    generatedOutline = outline;
    var text = JSON.stringify(outline, null, 2);
    downloadFile(text, outlineStorageTitle(outline) + "_" + today() + "_outline.json", "application/json");
    setStatus("纪要 JSON 已下载。", "success");
  });

  $("#outlineEditor").on("click", ".outline-section-nav-item", function () {
    generatedOutline = collectOutlineFromEditor();
    activeOutlineSectionIndex = parseInt($(this).data("section"), 10) || 0;
    renderOutlineEditor(generatedOutline);
  });

  $("#outlineEditor").on("keydown", ".outline-section-nav-item", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    $(this).trigger("click");
  });

  $("#outlineEditor").on("click", ".outline-page-index-item", function (event) {
    event.preventDefault();
    event.stopPropagation();
    var sectionIndex = parseInt($(this).data("section"), 10);
    var frameIndex = parseInt($(this).data("frame"), 10);
    if (Number.isNaN(sectionIndex) || Number.isNaN(frameIndex)) return;
    generatedOutline = collectOutlineFromEditor();
    activeOutlineSectionIndex = sectionIndex;
    renderOutlineEditor(generatedOutline);
    setTimeout(function () {
      var $detail = $("#outlineEditor .outline-section-detail");
      var $frame = $("#outline-frame-" + sectionIndex + "-" + frameIndex);
      if (!$detail.length || !$frame.length) return;
      var nextTop = $detail.scrollTop() + $frame.position().top - 10;
      $detail.animate({ scrollTop: Math.max(0, nextTop) }, 160);
      $frame.addClass("outline-frame-jump-highlight");
      setTimeout(function () {
        $frame.removeClass("outline-frame-jump-highlight");
      }, 900);
    }, 0);
  });

  $("#outlineEditor").on("click", ".outline-add-frame", function () {
    var outline = collectOutlineFromEditor();
    var sectionIndex = parseInt($(this).closest(".outline-section").data("section"), 10);
    if (outline.sections[sectionIndex]) {
      var nextFrame = outline.sections[sectionIndex].frames.length + 1;
      outline.sections[sectionIndex].frames.push({
        title: "User Added Frame " + nextFrame,
        summary: "用户新增 frame：请根据本大节 Markdown 内容生成这一页。",
        key_points: ["保留该新增 frame", "结合本大节知识点展开"],
      });
    }
    renderOutlineEditor(outline);
  });

  $("#outlineEditor").on("click", ".outline-remove-frame", function () {
    var outline = collectOutlineFromEditor();
    var $section = $(this).closest(".outline-section");
    var sectionIndex = parseInt($section.data("section"), 10);
    var frameIndex = parseInt($(this).closest(".outline-frame").data("frame"), 10);
    if (outline.sections[sectionIndex]) {
      outline.sections[sectionIndex].frames.splice(frameIndex, 1);
      if (!outline.sections[sectionIndex].frames.length) {
        outline.sections[sectionIndex].frames.push({ title: "New Frame", summary: "", key_points: [] });
      }
    }
    renderOutlineEditor(outline);
  });

  $("#outlineEditor").on("click", ".outline-remove-section", function () {
    var outline = collectOutlineFromEditor();
    var sectionIndex = parseInt($(this).closest(".outline-section").data("section"), 10);
    outline.sections.splice(sectionIndex, 1);
    activeOutlineSectionIndex = Math.max(0, Math.min(sectionIndex, outline.sections.length - 1));
    renderOutlineEditor(outline);
  });

  $("#outlineEditor").on("click", ".outline-save-section", function () {
    generatedOutline = collectOutlineFromEditor();
    renderOutlineEditor(generatedOutline);
    setStatus("本节纪要已保存。", "success");
  });

  $("#outlineEditor").on("change", ".outline-section-count", function (event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    var sectionIndex = parseInt($(this).closest(".outline-section").data("section"), 10);
    var nextCount = Math.max(1, Math.min(80, parseInt($(this).val(), 10) || 1));
    var outline = collectOutlineFromEditor();
    var section = outline.sections[sectionIndex];
    if (!section) return;
    section.frames = section.frames || [];
    while (section.frames.length < nextCount) {
      section.frames.push({
        title: "New Frame " + (section.frames.length + 1),
        summary: "",
        key_points: [],
      });
    }
    if (section.frames.length > nextCount) {
      section.frames = section.frames.slice(0, nextCount);
    }
    section.slide_count = section.frames.length;
    activeOutlineSectionIndex = sectionIndex;
    renderOutlineEditor(outline);
    setStatus("本节页数已调整为 " + nextCount + " 页。", "success");
  });

  $("#outlineEditor").on("click", ".outline-refresh-section", function () {
    if (isGenerating) return;
    var $button = $(this);
    var sectionIndex = parseInt($button.closest(".outline-section").data("section"), 10);
    var outline = collectOutlineFromEditor();
    var section = outline.sections[sectionIndex];
    if (!section) return;
    var content = $("#content").val().trim();
    if (!content) {
      setStatus("请先导入 .md/.markdown 知识图谱文件", "error");
      return;
    }
    var payload = buildBaseGenerationPayload(content);
    if (!payload) return;
    payload.section_id = section.id;
    payload.slide_count = Math.max(1, Math.min(80, (section.frames && section.frames.length) || section.slide_count || 1));
    setGenerating(true);
    $button.prop("disabled", true).text("刷新中...");
    setStatus("正在刷新大节 " + (section.id || sectionIndex + 1) + " 的纪要...", "info");
    fetch("/beamer-generator/api/regenerate-outline-section", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          if (!resp.ok || data.error || data.detail) throw new Error(data.detail || data.error || resp.statusText);
          return data;
        });
      })
      .then(function (data) {
        outline.sections[sectionIndex] = data.section;
        renderOutlineEditor(normalizeOutlineFrameCounts(outline));
        setStatus("大节纪要已刷新。", "success");
      })
      .catch(function (err) {
        setStatus("大节纪要刷新失败: " + err.message, "error");
      })
      .finally(function () {
        setGenerating(false);
      });
  });

  $("#outlineEditor").on("input change", "input, textarea", function () {
    generatedOutline = collectOutlineFromEditor();
    updateOutlineSummary();
    refreshOutlineMathPreviews($(this).closest(".outline-section"));
    schedulePageChecklistUpdate(fullLatex, 260);
  });

  $("#btnGenerateOutline").on("click", function () {
    if (isGenerating) return;
    var content = $("#content").val().trim();
    if (!content) {
      setStatus("请先导入 .md/.markdown 知识图谱文件", "error");
      return;
    }
    var payload = buildBaseGenerationPayload(content);
    if (!payload) return;
    setGenerating(true);
    $("#btnGenerateOutline").prop("disabled", true).text("生成纪要中...");
    startOutlineProgress("正在提交纪要生成请求...");
    fetch("/beamer-generator/api/generate-outline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (resp) {
        setOutlineProgress(Math.max(outlineGenerateProgress, 18), "已连接后端，正在等待 GPT 返回纪要...");
        return resp.json().then(function (data) {
          if (!resp.ok) throw new Error(data.detail || data.error || ("HTTP " + resp.status));
          return data;
        });
      })
      .then(function (data) {
        setOutlineProgress(94, "已收到纪要，正在渲染可编辑目录...");
        var outline = requireRenderableOutline(data && data.outline);
        activeOutlineSectionIndex = 0;
        renderOutlineEditor(outline);
        $("#tabOutline").prop("disabled", false);
        setActiveTab("outline");
        finishOutlineProgress("纪要生成完成，请检查并修改后生成 LaTeX。", "success");
        setStatus("纪要已生成，请检查并修改后点击右上角生成 LaTeX。", "success");
      })
      .catch(function (err) {
        finishOutlineProgress("纪要生成失败：" + err.message, "error");
        setStatus("纪要生成失败: " + err.message, "error");
      })
      .finally(function () {
        setGenerating(false);
        $("#btnGenerateOutline").prop("disabled", false).text("生成纪要");
      });
  });

  $("#btnGenerate").on("click", function () {
    if (isGenerating) return;

    var content = $("#content").val().trim();
    if (!content) {
      setStatus("请先导入 .md/.markdown 知识图谱文件", "error");
      return;
    }
    if (!generatedOutline || !generatedOutline.sections || !generatedOutline.sections.length) {
      setStatus("请先点击“生成纪要”，确认或修改后再生成演示文稿。", "error");
      $("#btnGenerateOutline").focus();
      return;
    }

    var previousLatex = fullLatex;
    var generatedLatex = "";
    var receivedFirstChunk = false;
    $("#tabPpt").prop("disabled", true);
    generatedOutline = collectOutlineFromEditor();
    var payload = buildBaseGenerationPayload(content);
    if (!payload) return;
    payload.outline = generatedOutline;
    setGenerating(true);
    updateLatexGenerateProgress(5, "正在根据已确认纪要生成 LaTeX...");

    var generateTimeoutMs = 900000;
    var abortCtrl = new AbortController();
    var timeoutId = setTimeout(function () {
      abortCtrl.abort();
      setGenerating(false);
      setStatus("生成超时，15 分钟无后端数据。若页数较多，请减少页数或分章节生成。", "error");
    }, generateTimeoutMs);

    function resetTimeout() {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(function () {
        abortCtrl.abort();
        setGenerating(false);
        setStatus("生成超时，15 分钟无后端数据。若页数较多，请减少页数或分章节生成。", "error");
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
        updateLatexGenerateProgress(12, "已连接 GPT，正在等待生成...");
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
                    setStatus("GPT 未返回内容，请检查 API Key、Base URL、模型名或网络", "error");
                  } else {
                    updateLatexGenerateProgress(100, "生成完成，共 " + fullLatex.length + " 字符");
                    setGenerating(false);
                    fullLatex = applyCustomRequirementOverrides(generatedLatex, currentCustomRequirements);
                    sourceLatex = fullLatex;
                    updateLatexEditor(fullLatex);
                    setActiveTab("latex");
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
                var heartbeatProgress = Math.max(latexGenerateProgress, receivedFirstChunk ? latexGenerateProgress : 18);
                updateLatexGenerateProgress(heartbeatProgress, d.content || "已连接，等待 GPT 生成...");
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
                  setStatus("GPT 未返回内容，请检查 API Key、Base URL、模型名或网络", "error");
                  return;
                }
                fullLatex = applyCustomRequirementOverrides(generatedLatex, currentCustomRequirements);
                sourceLatex = fullLatex;
                updateLatexEditor(fullLatex);
                setActiveTab("latex");
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
    if (latexHasExternalGraphicRefs(fullLatex) && Object.keys(buildFigureAssetPayload()).length) {
      setStatus("当前 LaTeX 引用了 fig 图片，正在下载包含图片的 Overleaf ZIP...", "info");
      postProjectJson(["/beamer-generator/api/overleaf-package", "/beamer-generator/api/overleaf-package/", "/api/overleaf-package"], buildOverleafPayload())
        .then(function (data) {
          if (!data || data.error || data.success === false || !data.snip_uri) {
            throw new Error((data && data.error) || "未生成 ZIP");
          }
          return fetch(data.snip_uri).then(function (resp) { return resp.blob(); }).then(function (blob) {
            downloadFile(blob, (data.filename || ("presentation_" + today() + "_overleaf.zip")), "application/zip");
            setStatus("已下载包含 main.tex 和 fig 图片的 Overleaf ZIP", "success");
          });
        })
        .catch(function (err) {
          setStatus("下载 Overleaf ZIP 失败: " + (err && err.message ? err.message : err), "error");
        });
      return;
    }
    downloadFile(fullLatex, "presentation_" + today() + ".tex", "application/x-tex");
    setStatus("操作完成", "success");
  });

  function buildOverleafPayload() {
    if (editor && editor.getValue) {
      fullLatex = editor.getValue();
      sourceLatex = fullLatex;
    }
    if (slidesData && $("#slideCanvas").find(":focus").length) {
      saveCurrentSlide();
      syncLatexFromSlides();
    }
    var payload = buildProjectSavePayload();
    if (!payload) {
      payload = {
        title: ($("#pptChapterTitleInput").val() || "Presentation"),
        subtitle: "",
        author: "",
        date: "",
        slides: [],
        figure_assets: buildFigureAssetPayload(),
        latex: fullLatex || "",
      };
    }
    payload.latex = fullLatex || payload.latex || "";
    payload.figure_assets = buildFigureAssetPayload();
    return payload;
  }

  $("#btnOpenOverleaf").on("click", function () {
    if (!fullLatex && editor && editor.getValue) {
      fullLatex = editor.getValue();
      sourceLatex = fullLatex;
    }
    if (!fullLatex || !fullLatex.trim()) {
      setStatus("没有可发送到 Overleaf 的 LaTeX 内容", "error");
      return;
    }

    var popupName = "kg_overleaf_" + Date.now();
    var popup = null;
    try {
      popup = window.open("about:blank", popupName);
      if (popup && popup.document) {
        popup.document.write("<p>正在打开 Overleaf...</p>");
        popup.document.close();
      }
    } catch (err) {
      popup = null;
    }

    var $button = $(this);
    var payload = buildOverleafPayload();
    $button.prop("disabled", true).text("正在打开...");
    setStatus("正在打包 Overleaf 项目...", "info");
    postProjectJson(["/beamer-generator/api/overleaf-package", "/beamer-generator/api/overleaf-package/", "/api/overleaf-package"], payload)
      .then(function (data) {
        if (!data || data.error || data.success === false || !data.snip_uri) {
          throw new Error((data && (data.error || data.detail)) || "Overleaf 项目包生成失败");
        }
        $("#overleafZipDataUri").val(data.snip_uri);
        $("#openOverleafForm").attr("target", popup ? popupName : "_blank")[0].submit();
        setStatus("已打开 Overleaf，请在新窗口继续编辑和编译", "success");
      })
      .catch(function (err) {
        if (popup && !popup.closed) popup.close();
        setStatus("打开 Overleaf 失败: " + err.message, "error");
      })
      .finally(function () {
        $button.prop("disabled", !fullLatex).text("在 Overleaf 中编辑");
      });
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
    if (isLatexImportMode) {
      setStatus("当前模式只保留 PPTX 转 LaTeX，不再执行高保真 PPT 渲染。", "info");
      return;
    }
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
        sourceLatex = data.latex || fullLatex;
        fullLatex = data.latex || buildLatexFromSlides(slidesData);
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
    return renderSlideMiniature(slide, pageIndex, "slide-thumb-preview");
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
            '<button type="button" class="slide-thumb-delete" title="删除该页" aria-label="删除第 ' + (idx + 1) + ' 页">&times;</button>' +
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
        renderSlideMiniatureMath($thumb);
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
    var renderedBg = slide.renderedBackground || "";
    var useRenderedBg = !!renderedBg && slide.backgroundMode !== "white";
    var $render = $('<div class="slide-render' + (slide.reviewBackground ? " review-background" : "") + (useRenderedBg ? " has-rendered-background" : "") + '" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "frame")) + '"></div>');
    if (useRenderedBg) {
      $render.append('<img class="slide-rendered-background" src="' + escAttr(renderedBg) + '" alt="" draggable="false" />');
    }
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

    if (slide.type === "title") {
      $render.append(
        '<div class="slide-title-credit slide-formula-host">' +
          '<textarea class="slide-title-credit-input slide-hidden-math-source" data-field="titleCredit" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "titleCredit")) + '" placeholder="作者 / 日期">' +
            escHtml(slide.titleCredit || "") +
          '</textarea>' +
          '<div class="slide-title-credit-rich slide-rich-text-preview" contenteditable="true" spellcheck="false" data-sync-key="' + escAttr(syncKey(currentSlideIdx, "titleCredit")) + '" data-math-source=".slide-title-credit-input"></div>' +
          '<div class="slide-formula-boxes slide-title-credit-formulas" data-formula-source=".slide-title-credit-input"></div>' +
        '</div>'
      );
    }

    var $body = $('<div class="slide-body' + (slide.hideParsedContent ? " slide-parsed-content-hidden" : "") + '"></div>');
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

    if (slide.missing_equations && slide.missing_equations.length > 0) {
      var $missing = $('<div class="slide-missing-equations"></div>');
      $.each(slide.missing_equations, function (_j, eq) {
        var label = (eq && (eq.label || eq.key)) || "Unknown equation";
        $missing.append(
          '<div class="slide-missing-equation">' +
            '<strong>缺失公式：</strong>' + escHtml(label) +
            '<span>请导入包含该公式的章节，系统会自动补全。</span>' +
          '</div>'
        );
      });
      $body.append($missing);
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
    $.each(slide.formulaBoxes || [], function (j, box) {
      $textboxes.append(createFormulaBox(j, box));
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
          '<button id="toolbarResetBgColor" class="toolbar-btn toolbar-mini toolbar-reset-btn" type="button" title="恢复当前页面白色背景">白底</button>' +
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
        '<div class="slide-callout-preview" style="font-size:' + fontSize + 'px;text-align:' + escAttr(align) + ';"></div>' +
        '<button class="slide-callout-remove" data-action="remove-callout" data-callout="' + idx + '">&times;</button>' +
        '<div class="slide-callout-resize-handle"></div>' +
      '</div>'
    );
    $box.find(".slide-callout-content").css("height", Math.max(28, height - 18) + "px");
    renderMathText($box.find(".slide-callout-preview"), repairPptLatexArtifacts(callout.text || "蓝色箭头框"), {
      displayMode: false,
      boxedMath: false,
      emptyText: "",
    });

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
        $box.find(".slide-callout-preview").css("min-height", Math.max(28, newH - 18) + "px");
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

  function createFormulaBox(idx, box) {
    box = box || {};
    var key = syncKey(currentSlideIdx, "formulaBox", idx);
    var width = clampNumber(box.width, 140, 780, 520);
    var height = clampNumber(box.height, 50, 300, 96);
    var x = clampNumber(box.x, 0, 800 - width, 120 + idx * 18);
    var y = clampNumber(box.y, 0, 450 - height, 178 + idx * 18);
    var fontSize = clampNumber(box.fontSize, 12, 36, 18);
    var formula = latexMathDisplaySource(box.formula || "");
    var $box = $(
      '<div class="slide-free-formula-box" data-sync-key="' + escAttr(key) + '" data-formula-box="' + idx + '" data-number="' + escAttr(box.number || "") + '" data-label="' + escAttr(box.label || "") + '" style="left:' + x + 'px;top:' + y + 'px;width:' + width + 'px;height:' + height + 'px;font-size:' + fontSize + 'px;">' +
        '<div class="slide-free-formula-drag" title="拖动公式框">::</div>' +
        '<textarea class="slide-free-formula-source slide-hidden-math-source" data-sync-key="' + escAttr(key) + '" data-formula-box-source="' + idx + '">' + escHtml(formula) + '</textarea>' +
        '<div class="slide-free-formula-preview" data-sync-key="' + escAttr(key) + '"></div>' +
        '<button class="slide-free-formula-remove" data-action="remove-formula-box" data-formula-box="' + idx + '">&times;</button>' +
        '<div class="slide-free-formula-resize-handle"></div>' +
      '</div>'
    );
    appendKatexNode($box.find(".slide-free-formula-preview").empty(), formula, true, formula);

    $box.on("dblclick", function (e) {
      if ($(e.target).is("button, .slide-free-formula-resize-handle, .slide-free-formula-drag")) return;
      e.stopPropagation();
      $box.toggleClass("is-editing", true);
      $box.find(".slide-free-formula-source").focus().select();
    });

    $box.find(".slide-free-formula-source").on("input", function () {
      var next = latexMathDisplaySource($(this).val());
      $box.find(".slide-free-formula-preview").empty();
      appendKatexNode($box.find(".slide-free-formula-preview"), next, true, next);
      saveCurrentSlide();
      scheduleLatexSync();
      scheduleHistoryCommit();
    }).on("blur", function () {
      setTimeout(function () {
        if (!$box.find(":focus").length) $box.removeClass("is-editing");
      }, 120);
    });

    $box.find(".slide-free-formula-drag").on("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origX = parseFloat($box.css("left")) || 0;
      var origY = parseFloat($box.css("top")) || 0;
      $box.addClass("dragging");
      $(document).on("mousemove.formuladrag", function (e2) {
        var parentW = $box.parent().width() || 860;
        var parentH = $box.parent().height() || 484;
        var boxW = cssPx($box, "width", width);
        var boxH = cssPx($box, "height", height);
        $box.css({
          left: clampNumber(origX + (e2.clientX - startX), 0, parentW - boxW, 0) + "px",
          top: clampNumber(origY + (e2.clientY - startY), 0, parentH - boxH, 0) + "px",
        });
      });
      $(document).on("mouseup.formuladrag", function () {
        $box.removeClass("dragging");
        $(document).off("mousemove.formuladrag mouseup.formuladrag");
        saveCurrentSlide();
        commitHistorySnapshot(false);
        scheduleLatexSync();
      });
    });

    $box.find(".slide-free-formula-resize-handle").on("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX;
      var startY = e.clientY;
      var origW = cssPx($box, "width", width);
      var origH = cssPx($box, "height", height);
      $(document).on("mousemove.formularesize", function (e2) {
        var parentW = $box.parent().width() || 860;
        var parentH = $box.parent().height() || 484;
        var left = parseFloat($box.css("left")) || 0;
        var top = parseFloat($box.css("top")) || 0;
        $box.css({
          width: Math.min(parentW - left, Math.max(140, origW + (e2.clientX - startX))) + "px",
          height: Math.min(parentH - top, Math.max(50, origH + (e2.clientY - startY))) + "px",
        });
      });
      $(document).on("mouseup.formularesize", function () {
        $(document).off("mousemove.formularesize mouseup.formularesize");
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
    var columnWidths = latexTableColumnWidths(table.columnSpec, (table.headers || []).length);
    var html = '<div class="slide-table-wrap">' +
      '<div class="slide-table-tools">' +
        '<button type="button" data-action="add-table-row" title="新增一行">+ 行</button>' +
        '<button type="button" data-action="add-table-col" title="新增一列">+ 列</button>' +
        '<button type="button" data-action="remove-table-row" title="删除最后一行">- 行</button>' +
        '<button type="button" data-action="remove-table-col" title="删除最后一列">- 列</button>' +
        '<button type="button" data-action="remove-table" title="删除当前表格">删除表格</button>' +
      '</div>' +
      '<table class="slide-table">';
    if (columnWidths.length) {
      html += '<colgroup>';
      $.each(columnWidths, function (_idx, width) {
        html += '<col style="width:' + escAttr(width) + '">';
      });
      html += '</colgroup>';
    }
    html += '<thead><tr>';
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

    $ctx.on("focus.slide", ".slide-item-input, .slide-textbox-content, .slide-callout-content, .slide-free-formula-source, .slide-eq-input, .slide-title-input, .slide-subtitle-input, .slide-title-credit-input, .slide-notes-input", function () {
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

    $ctx.on("mousedown.slide", ".slide-item-input, .slide-textbox-content, .slide-callout-content, .slide-free-formula-source, .slide-eq-input, .slide-title-input, .slide-subtitle-input, .slide-title-credit-input, .slide-notes-input, .slide-placeholder-label, [data-th], [data-tr], [data-tc]", function (e) {
      e.stopPropagation();
    });

    $ctx.on("blur.slide", ".slide-item-input, .slide-textbox-content, .slide-callout-content, .slide-free-formula-source, .slide-eq-input", function () {
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

    $ctx.on("click.slide", ".slide-title-input, .slide-subtitle-input, .slide-title-credit-input, .slide-item-input, .slide-eq-input, .slide-notes-input, .slide-textbox-content, .slide-callout-content, .slide-free-formula-source, .slide-placeholder-label, [data-th], [data-tr], [data-tc]", function (e) {
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

    $ctx.on("input.slide change.slide", ".slide-title-input, .slide-subtitle-input, .slide-title-credit-input, .slide-item-input, .slide-eq-input, .slide-notes-input, .slide-textbox-content, .slide-callout-content, .slide-free-formula-source, .slide-rich-text-preview, .slide-placeholder-label, [data-th], [data-tr], [data-tc]", function () {
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
        if (Date.now() < toolbarSelectionHoldUntil || $(".slide-toolbar").find(document.activeElement).length) {
          return;
        }
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
      slide.backgroundMode = "review";
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

    $ctx.on("click.slide", '[data-action="remove-formula-box"]', function (e) {
      e.stopImmediatePropagation();
      var idx = parseInt($(this).data("formula-box"), 10);
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      if (!Array.isArray(slide.formulaBoxes)) slide.formulaBoxes = [];
      slide.formulaBoxes.splice(idx, 1);
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
    });
  }

  function normalizeParsedSlidesData(data, previousSlidesData) {
    if (!data || !Array.isArray(data.slides)) return null;
    if (!Array.isArray(data.missing_equations)) data.missing_equations = [];
    if (!Array.isArray(data.resolved_equations)) data.resolved_equations = [];
    if (data.slides[0] && data.slides[0].type === "title") {
      if (!data.slides[0].title) data.slides[0].title = data.title || "";
      if (!data.slides[0].subtitle) data.slides[0].subtitle = data.subtitle || "";
      if (!data.slides[0].titleCredit) {
        data.slides[0].titleCredit = [data.author || "", data.date || ""].filter(Boolean).join("\n");
      }
    }
    for (var i = 0; i < data.slides.length; i++) {
      if (!data.slides[i].images) data.slides[i].images = [];
      if (!data.slides[i].textboxes) data.slides[i].textboxes = [];
      if (!data.slides[i].formulaBoxes) data.slides[i].formulaBoxes = [];
      if (!data.slides[i].callouts) data.slides[i].callouts = [];
      if (!Array.isArray(data.slides[i].missing_equations)) data.slides[i].missing_equations = [];
      normalizeSlideEditableText(data.slides[i]);
      data.slides[i].placeholders = normalizePlaceholders(data.slides[i].placeholders);
      if (data.slides[i].table) data.slides[i].table = normalizeTable(data.slides[i].table);
    }
    if (previousSlidesData) mergeEditedImagePositions(data, previousSlidesData);
    ensureAllSlideFigurePlaceholders(data);
    return data;
  }

  function applyRenderedPagesToSlides(data, renderedPages, options) {
    data = data || {};
    renderedPages = Array.isArray(renderedPages) ? renderedPages : [];
    options = options || {};
    if (!Array.isArray(data.slides)) data.slides = [];
    if (!data.slides.length && renderedPages.length) {
      data.slides = renderedPages.map(function (_, idx) {
        return {
          id: idx,
          type: idx === 0 ? "title" : "content",
          title: "页面 " + (idx + 1),
          subtitle: "",
          items: [],
          equations: [],
          table: null,
          notes: "",
          images: [],
          placeholders: [],
          textboxes: [],
          formulaBoxes: [],
          callouts: [],
        };
      });
    }
    renderedPages.forEach(function (page, idx) {
      if (!data.slides[idx]) {
        data.slides[idx] = {
          id: idx,
          type: "content",
          title: "页面 " + (idx + 1),
          subtitle: "",
          items: [],
          equations: [],
          table: null,
          notes: "",
          images: [],
          placeholders: [],
          textboxes: [],
          formulaBoxes: [],
          callouts: [],
        };
      }
      data.slides[idx].renderedBackground = page.image || "";
      data.slides[idx].renderedBackgroundWidth = page.width || 0;
      data.slides[idx].renderedBackgroundHeight = page.height || 0;
      data.slides[idx].backgroundMode = "latex-rendered";
      data.slides[idx].latexRenderedPage = true;
      data.slides[idx].hideParsedContent = options.hideParsedContent !== false;
      if (data.slides[idx].hideParsedContent) {
        data.slides[idx].title = "页面 " + (idx + 1);
        data.slides[idx].subtitle = "";
        data.slides[idx].titleCredit = "";
        data.slides[idx].items = [];
        data.slides[idx].itemRichHtml = [];
        data.slides[idx].equations = [];
        data.slides[idx].missing_equations = [];
        data.slides[idx].table = null;
        data.slides[idx].notes = "";
        data.slides[idx].images = [];
        data.slides[idx].placeholders = [];
        data.slides[idx].textboxes = [];
        data.slides[idx].formulaBoxes = [];
        data.slides[idx].callouts = [];
      }
    });
    for (var i = 0; i < data.slides.length; i++) {
      data.slides[i].id = i;
    }
    return data;
  }

  function finishEditablePptLoad(data, options, statusPrefix) {
    options = options || {};
    slidesData = normalizeParsedSlidesData(data, null);
    if (!slidesData) {
      setStatus("解析失败: 未识别到幻灯片结构", "error");
      return;
    }
    if (options.chapterTitle) {
      slidesData.chapter_title = options.chapterTitle;
      slidesData.title = slidesData.title || options.chapterTitle;
      $("#pptChapterTitleInput").val(options.chapterTitle);
    }
    var renderedPageMode = hasRenderedLatexPages(slidesData);
    if (renderedPageMode) {
      inputCollapsed = true;
      localStorage.setItem("bg_input_panel_collapsed", "1");
    }
    sourceLatex = fullLatex;
    if (!renderedPageMode) {
      fullLatex = buildLatexFromSlides(slidesData);
      sourceLatex = fullLatex;
      updateLatexEditor(fullLatex);
      rebuildLatexSyncMapFromSource(slidesData, fullLatex);
    } else if (!isLatexImportMode) {
      rebuildLatexSyncMapFromSource(slidesData, fullLatex);
    } else {
      rebuildRenderedPageLocationMap(slidesData, fullLatex);
    }
    currentSlideIdx = slidesData.slides.length > 0 ? 0 : -1;
    resetHistory();
    $("#tabPpt").prop("disabled", false);
    updateDownloadPptxButton();
    setActiveTab("ppt");
    if (renderedPageMode) {
      applyInputCollapsedState();
    }
    renderSlideList();
    if (currentSlideIdx >= 0) selectSlide(currentSlideIdx);
    setStatus((statusPrefix || "生成完成") + "，共 " + slidesData.slides.length + " 页幻灯片", "success");
    updateLatexImportMeta(importedLatexFileName || importedPdfFileName
      ? "已导入：" + (importedLatexFileName || importedPdfFileName) + "。左侧显示 LaTeX 源码；右侧以 PDF 页面为底图，可添加和编辑覆盖层内容。"
      : (renderedPageMode ? "已按编译 PDF 页面渲染为 PPT；右侧可添加和编辑覆盖层内容。" : "已从左侧内容生成可编辑 PPT"));
  }

  function loadOverleafZipIntoEditablePpt(file, options) {
    options = options || {};
    if (!file) return $.Deferred().reject(new Error("未选择文件")).promise();
    importedLatexFileName = file.name || "";
    importedPdfFileName = "";
    var formData = new FormData();
    formData.append("file", file);
    setStatus("正在导入 Overleaf 源码包...", "info");

    return $.ajax({
      url: "/beamer-generator/api/import-overleaf-package",
      method: "POST",
      data: formData,
      processData: false,
      contentType: false,
      success: function (data) {
        if (!data || data.error || !data.latex) {
          setStatus("Overleaf ZIP 导入失败: " + ((data && data.error) || "未读取到 LaTeX 文件"), "error");
          return;
        }
        importedLatexFileName = data.tex_filename || importedLatexFileName;
        fullLatex = data.latex || "";
        sourceLatex = fullLatex;
        updateLatexEditor(fullLatex);
        $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf").prop("disabled", !fullLatex.trim());
        $("#btnConvertPpt, #btnDownloadPptx").hide().prop("disabled", true);
        if (data.asset_urls) {
          setPackageImages(data.asset_urls);
        }
        var title = options.chapterTitle || titleFromLatexFileName(importedLatexFileName) || titleFromLatexFileName(file.name || "") || "Overleaf 演示文稿";
        if (Array.isArray(data.rendered_pages) && data.rendered_pages.length) {
          setImportedPreviewImages(renderedPagesToPreviewImages(data.rendered_pages, "Overleaf 页面"), "Overleaf 导入预览");
          applyRenderedPagesToSlides(data, data.rendered_pages, { hideParsedContent: true });
          finishEditablePptLoad(data, { chapterTitle: title }, "Overleaf 导入完成");
          return;
        }
        finishEditablePptLoad(data, { chapterTitle: title }, "Overleaf 源码解析完成");
        if (data.render_error) {
          setStatus("Overleaf ZIP 已导入，但本地未能高保真渲染：" + data.render_error + "。可改为导入 Overleaf 下载的 PDF。", "error");
        }
      },
      error: function (xhr) {
        var msg = ajaxErrorMessage(xhr, "导入请求失败");
        setStatus("Overleaf ZIP 导入失败: " + msg, "error");
      },
    });
  }

  function loadPdfIntoEditablePpt(file, options) {
    options = options || {};
    if (!file) return;
    importedPdfFileName = file.name || "";
    importedLatexFileName = "";
    var formData = new FormData();
    formData.append("file", file);
    fullLatex = "% PDF 高保真页面背景：" + (importedPdfFileName || "presentation.pdf") + "\n";
    sourceLatex = fullLatex;
    updateLatexEditor(fullLatex);
    $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf, #btnConvertPpt").prop("disabled", false);
    setStatus("正在把 PDF 页面渲染成高保真 PPT 页面...", "info");

    $.ajax({
      url: "/beamer-generator/api/render-pdf-pages",
      method: "POST",
      data: formData,
      processData: false,
      contentType: false,
      success: function (data) {
        if (!data || data.error || !Array.isArray(data.rendered_pages) || !data.rendered_pages.length) {
          setStatus("PDF 渲染失败: " + ((data && data.error) || "未生成页面图片"), "error");
          return;
        }
        var title = options.chapterTitle || titleFromLatexFileName(importedPdfFileName) || "PDF 演示文稿";
        var pptData = {
          title: title,
          chapter_title: title,
          slides: [],
        };
        setImportedPreviewImages(renderedPagesToPreviewImages(data.rendered_pages, "PDF 页面"), "PDF 导入预览");
        applyRenderedPagesToSlides(pptData, data.rendered_pages, { hideParsedContent: true });
        finishEditablePptLoad(pptData, { chapterTitle: title }, "PDF 渲染完成");
      },
      error: function (xhr) {
        var msg = ajaxErrorMessage(xhr, "渲染请求失败");
        setStatus("PDF 渲染失败: " + msg, "error");
      },
    });
  }

  function loadPptIntoLatexFromFile(file, options) {
    options = options || {};
    if (!file) return $.Deferred().reject(new Error("未选择文件")).promise();
    if (!/\.pptx$/i.test(file.name || "")) {
      return $.Deferred().reject(new Error("请选择 .pptx 文件")).promise();
    }

    var formData = new FormData();
    formData.append("file", file);
    importedLatexFileName = (file.name || "presentation.pptx").replace(/\.pptx$/i, ".tex");
    importedPdfFileName = "";
    setStatus("正在导入 PPTX 并转换为 LaTeX...", "info");

    return $.ajax({
      url: "/beamer-generator/api/import-ppt-latex",
      method: "POST",
      data: formData,
      processData: false,
      contentType: false,
      success: function (data) {
        if (!data || data.error || !data.latex) {
          setStatus("PPTX 转 LaTeX 失败: " + ((data && data.error) || "未生成 LaTeX"), "error");
          return;
        }
        fullLatex = data.latex || "";
        sourceLatex = fullLatex;
        updateLatexEditor(fullLatex);
        $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf, #btnConvertPpt").prop("disabled", !fullLatex.trim());
        if (data.asset_urls) {
          setPackageImages(data.asset_urls);
        }
        var title = options.chapterTitle || titleFromLatexFileName(file.name || importedLatexFileName);
        setImportedPreviewImages(figureAssetsToPreviewImages(data.figure_assets), "PPT 图片/公式预览");
        $("#pptChapterTitleInput").val(title || "");
        setActiveTab("latex");
        var imageCount = Array.isArray(data.figure_assets) ? data.figure_assets.length : 0;
        updateLatexImportMeta("已导入：" + (file.name || "PPTX") + "。已按页面元素转换为 LaTeX；图片保留为 Figure 编号和 fig 路径占位框，公式截图与蓝色注释框保留原页位置。");
        setStatus("PPTX 转 LaTeX 完成：共 " + (data.slide_count || 0) + " 页，图片 " + imageCount + " 张；可点击“预览导入内容”查看缩略图。", "success");
      },
      error: function (xhr) {
        var msg = ajaxErrorMessage(xhr, "转换请求失败");
        setStatus("PPTX 转 LaTeX 失败: " + msg, "error");
      },
    });
  }

  function loadLatexProjectIntoEditablePpt(files, options) {
    options = options || {};
    files = Array.prototype.slice.call(files || []);
    if (!files.length) return;

    var texFiles = files.filter(function (file) {
      return /\.(tex|latex)$/i.test(file.name || "") || /\.(tex|latex)$/i.test(file.webkitRelativePath || "");
    });
    if (!texFiles.length) {
      setStatus("LaTeX 项目目录中未找到 .tex 文件", "error");
      return;
    }

    var formData = new FormData();
    files.forEach(function (file) {
      var relPath = file.webkitRelativePath || file.name;
      formData.append("files", file, relPath);
    });
    setStatus("正在上传并编译 LaTeX 项目目录...", "info");

    return $.ajax({
      url: "/beamer-generator/api/render-latex-project",
      method: "POST",
      data: formData,
      processData: false,
      contentType: false,
      success: function (data) {
        if (!data || data.error || !data.latex || !Array.isArray(data.rendered_pages) || !data.rendered_pages.length) {
          setStatus("LaTeX 项目渲染失败: " + ((data && data.error) || "未生成页面图片"), "error");
          return;
        }
        importedLatexFileName = data.tex_filename || data.filename || importedLatexFileName || "presentation.tex";
        importedPdfFileName = "";
        fullLatex = data.latex || "";
        sourceLatex = fullLatex;
        updateLatexEditor(fullLatex);
        $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf, #btnConvertPpt").prop("disabled", !fullLatex.trim());
        if (data.asset_urls) {
          setPackageImages(data.asset_urls);
        }
        var title = options.chapterTitle || titleFromLatexFileName(importedLatexFileName) || "LaTeX 演示文稿";
        setImportedPreviewImages(renderedPagesToPreviewImages(data.rendered_pages, "LaTeX 页面"), "LaTeX 项目预览");
        applyRenderedPagesToSlides(data, data.rendered_pages, { hideParsedContent: true });
        finishEditablePptLoad(data, { chapterTitle: title }, "LaTeX 项目渲染完成");
      },
      error: function (xhr) {
        var msg = ajaxErrorMessage(xhr, "渲染请求失败");
        setStatus("LaTeX 项目渲染失败: " + msg + "。请确认已选择包含图片、样式文件和主 .tex 的完整目录。", "error");
      },
    });
  }

  function loadLatexIntoEditablePpt(tex, options) {
    options = options || {};
    tex = String(tex || "");
    if (!tex.trim()) {
      setStatus("请先导入或粘贴 LaTeX 代码", "error");
      return;
    }
    fullLatex = tex;
    sourceLatex = fullLatex;
    if (options.updateEditor !== false) updateLatexEditor(fullLatex);
    $("#btnCopy, #btnDownloadTex, #btnOpenOverleaf, #btnConvertPpt").prop("disabled", false);
    setStatus(isLatexImportMode ? "正在渲染 LaTeX 页面..." : "正在解析 LaTeX 结构...", "info");

    if (isLatexImportMode) {
      $.ajax({
        url: "/beamer-generator/api/render-latex-pages",
        method: "POST",
        contentType: "application/json",
        data: JSON.stringify({ latex: fullLatex, filename: importedLatexFileName || "presentation.tex", asset_urls: importedPackageAssetUrls || {} }),
        success: function (data) {
          if (!data || data.error || !Array.isArray(data.rendered_pages) || !data.rendered_pages.length) {
            setStatus("高保真渲染失败: " + ((data && data.error) || "未生成页面图片"), "error");
            return;
          }
          setImportedPreviewImages(renderedPagesToPreviewImages(data.rendered_pages, "渲染页面"), "导入内容预览");
          applyRenderedPagesToSlides(data, data.rendered_pages, { hideParsedContent: true });
          finishEditablePptLoad(data, options, "高保真渲染完成");
        },
        error: function (xhr) {
          var msg = ajaxErrorMessage(xhr, "渲染请求失败");
          setStatus("高保真渲染失败: " + msg + "。请先修复 LaTeX 编译错误，或导入已经编译成功的 PDF 文件。", "error");
        },
      });
      return;
    }

    $.ajax({
      url: "/beamer-generator/api/parse-slides",
      method: "POST",
      contentType: "application/json",
      data: JSON.stringify({ latex: fullLatex }),
      success: function (data) {
        if (!data || data.error || !data.slides) {
          setStatus("解析失败: " + ((data && data.error) || "未识别到幻灯片结构"), "error");
          return;
        }
        if (data.latex && data.latex !== fullLatex) {
          fullLatex = data.latex;
          sourceLatex = fullLatex;
          if (options.updateEditor !== false) updateLatexEditor(fullLatex);
        }
        finishEditablePptLoad(data, options, "解析完成");
      },
      error: function () {
        setStatus("解析请求失败", "error");
      },
    });
  }

  function bindToolbarEvents($ctx) {
    $ctx.off("input.toolbar change.toolbar mousedown.toolbar pointerdown.toolbar focusin.toolbar click.toolbar");

    function holdRichTextSelectionForToolbar() {
      toolbarSelectionHoldUntil = Date.now() + 1200;
      rememberCurrentRichTextSelection();
    }

    $ctx.on("pointerdown.toolbar mousedown.toolbar focusin.toolbar", ".slide-toolbar input, .slide-toolbar select, .slide-toolbar button", function (e) {
      holdRichTextSelectionForToolbar();
      if (this.tagName === "BUTTON") e.preventDefault();
    });

    $ctx.on("mouseup.toolbar keyup.toolbar focusin.toolbar", ".slide-rich-text-preview, .slide-rich-text-preview *", function () {
      setTimeout(function () {
        if (Date.now() < toolbarSelectionHoldUntil) return;
        syncToolbarFontSizeFromSelection();
      }, 0);
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
      holdRichTextSelectionForToolbar();
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
      e.stopImmediatePropagation();
      if (!slidesData || currentSlideIdx < 0 || !slidesData.slides[currentSlideIdx]) return;
      var textboxIdx = lastFocusedTextbox ? parseInt($(lastFocusedTextbox).data("tb"), 10) : NaN;
      saveCurrentSlide();
      var slide = slidesData.slides[currentSlideIdx];
      slide.reviewBackground = false;
      slide.backgroundMode = slide.renderedBackground ? "latex-rendered" : "";
      if (!Number.isNaN(textboxIdx) && slide.textboxes && slide.textboxes[textboxIdx]) {
        slide.textboxes[textboxIdx].bg = "#ffffff";
      }
      $("#toolbarBgColor").val("#ffffff");
      renderSlideEditor(slide);
      renderSlideList();
      commitHistorySnapshot(false);
      scheduleLatexSync();
      setStatus("已恢复当前页面白色背景", "success");
    });

    $ctx.on("change.toolbar", "#toolbarFontSize", function () {
      holdRichTextSelectionForToolbar();
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
      syncToolbarFontSizeFromSelection();
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

  $("#pptLatexImporter").on("change", function () {
    var file = this.files && this.files[0];
    if (!file) return;
    if (!/\.pptx$/i.test(file.name || "")) {
      setStatus("请选择 .pptx 文件", "error");
      $(this).val("");
      return;
    }

    $("#btnImportPptLatex").prop("disabled", true).text("转换中...");
    $("#btnImportPptInLatexPanel").prop("disabled", true).text("转换中...");
    loadPptIntoLatexFromFile(file, {
      chapterTitle: titleFromLatexFileName(file.name || ""),
    }).always(function () {
        $("#btnImportPptLatex").prop("disabled", false).text("导入 PPTX 转 LaTeX");
        $("#btnImportPptInLatexPanel").prop("disabled", false).text("导入 PPTX 转 LaTeX");
        $("#pptLatexImporter").val("");
    });
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

    var creditVal = $canvas.find('[data-field="titleCredit"]').val();
    if (creditVal !== undefined) slide.titleCredit = creditVal;
    if (slide.type === "title" && creditVal !== undefined && slidesData) {
      var creditLines = String(creditVal || "").split(/\r?\n/).map(function (line) { return line.trim(); }).filter(Boolean);
      if (creditLines.length) slidesData.author = creditLines[0];
      if (creditLines.length > 1) slidesData.date = creditLines.slice(1).join(" ");
    }

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
      slide.table.columnSpec = slide.table.columnSpec || "";
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
      var figureKey = normalizeFigureLabel(figure || label);
      var mappedFigure = figureKey ? figurePreviewMap[figureKey] : null;
      var asset = $ph.data("asset") || (mappedFigure && mappedFigure.url) || pickPackageImageForFigure(figure || label) || "";
      placeholders.push({
        type: "image",
        label: label,
        figure: figure,
        asset: asset,
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

    var formulaBoxes = [];
    $canvas.find(".slide-free-formula-box").each(function () {
      var $box = $(this);
      var $source = $box.find(".slide-free-formula-source");
      var formula = latexMathDisplaySource($source.val());
      if (!formula) return;
      formulaBoxes.push({
        formula: formula,
        number: $box.data("number") || "",
        label: $box.data("label") || "",
        fontSize: parseInt($box.css("font-size"), 10) || 18,
        width: fromSlidePx(cssPx($box, "width", 520), renderScale),
        height: fromSlidePx(cssPx($box, "height", 96), renderScale),
        x: fromSlidePx(parseFloat($box.css("left")) || 0, renderScale),
        y: fromSlidePx(parseFloat($box.css("top")) || 0, renderScale),
      });
    });
    slide.formulaBoxes = formulaBoxes;

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

    if (idx < currentSlideIdx) {
      currentSlideIdx -= 1;
    }
    if (currentSlideIdx >= slidesData.slides.length) {
      currentSlideIdx = slidesData.slides.length - 1;
    }

    renderSlideList();
    if (currentSlideIdx >= 0) selectSlide(currentSlideIdx);
    commitHistorySnapshot(false);
    scheduleLatexSync();
    setStatus("已删除第 " + (idx + 1) + " 页", "success");
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
      formulaBoxes: [],
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
        upsertSavedPptProject(data);
        return loadSavedPptProjects({ openAfterLoad: true, selectedChapterId: data.chapter_id }).then(function () {
          upsertSavedPptProject(data);
          setStatus("保存完成：已保存到左侧“选择已保存章节”中（" + (data.chapter_title || enteredTitle) + "）", "success");
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
    setStatus("正在按网页端样式捕获 PPT 页面...", "info");
    delete payload.latex;

    buildRenderedSlideSnapshots()
      .then(function (renderedSlides) {
        if (renderedSlides.length) {
          payload.rendered_slides = renderedSlides;
        }
        setStatus("正在生成 PPTX 文件...", "info");
        return postProjectBlob(["/beamer-generator/api/export-pptx", "/beamer-generator/api/export-pptx/", "/api/export-pptx"], payload);
      })
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
      if (!isLatexImportMode) {
        $("#btnGenerate").click();
      }
    }
  });

  restoreGptConfigFromBrowser();
  applyLatexImportMode();
  $("#savedLectureSelect, #btnRefreshSavedLectures").hide();
  $("#btnImportMarkdown").text("导入 MD 知识图谱");
  renderMarkdownImportList();
  removeLegacySavedPptLoadButton();
  loadSavedPptProjects();
  setupColumnResize();
  collapsedPaneResize = setupCollapsedPaneResize();
  updateContentPreview();
  setActiveTab("latex");
  applyInputCollapsedState();
  setGenerating(false);
  updateDownloadPptxButton();
});
