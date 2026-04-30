(function () {
    "use strict";

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function escapeAttribute(value) {
        return escapeHtml(value).replace(/`/g, "&#96;");
    }

    function sanitizeHref(value) {
        var href = String(value || "").trim();
        if (/^(https?:|mailto:|#|\/)/i.test(href)) {
            return href;
        }
        return "#";
    }

    function normalizeLatexText(value) {
        return String(value == null ? "" : value)
            .replace(/\\\\([()[\]])/g, "\\$1")
            .replace(/\\\\([A-Za-z]+)/g, "\\$1")
            .replace(/\\\\([{}_^])/g, "\\$1")
            .replace(/\\\\begin\{/g, "\\begin{")
            .replace(/\\\\end\{/g, "\\end{");
    }

    function protectMath(text) {
        var tokens = [];

        function stash(match) {
            var key = "@@MATH_" + tokens.length + "@@";
            tokens.push(match);
            return key;
        }

        var protectedText = normalizeLatexText(text)
            .replace(/\\begin\{(equation\*?|align\*?|gather\*?)\}[\s\S]*?\\end\{\1\}/g, stash)
            .replace(/\$\$[\s\S]*?\$\$/g, stash)
            .replace(/\\\[[\s\S]*?\\\]/g, stash)
            .replace(/\\\([\s\S]*?\\\)/g, stash)
            .replace(/(^|[^\\])(\$[^$\n]+?\$)/g, function (match, prefix, math) {
                return prefix + stash(math);
            });

        return {
            text: protectedText,
            tokens: tokens
        };
    }

    function restoreMath(html, tokens) {
        return html.replace(/@@MATH_(\d+)@@/g, function (match, index) {
            return escapeHtml(tokens[Number(index)] || match);
        });
    }

    function renderInline(input) {
        var protectedMath = protectMath(input);
        var html = escapeHtml(protectedMath.text);

        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
        html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
        html = html.replace(/(^|[^\*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
        html = html.replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");
        html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (match, label, href) {
            var safeHref = sanitizeHref(href);
            return '<a href="' + escapeAttribute(safeHref) + '" target="_blank" rel="noopener">' + label + "</a>";
        });

        return restoreMath(html, protectedMath.tokens);
    }

    function isBlank(line) {
        return /^\s*$/.test(line);
    }

    function isFence(line) {
        return /^\s*```/.test(line);
    }

    function isTableSeparator(line) {
        return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
    }

    function isBlockStart(line, nextLine) {
        return isBlank(line) ||
            isFence(line) ||
            /^\s{0,3}#{1,6}\s+/.test(line) ||
            /^\s{0,3}>\s?/.test(line) ||
            /^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line) ||
            /^\s*[-*+]\s+/.test(line) ||
            /^\s*\d+[.)]\s+/.test(line) ||
            (/\|/.test(line) && nextLine && isTableSeparator(nextLine));
    }

    function splitTableRow(line) {
        var text = line.trim();
        if (text.charAt(0) === "|") text = text.slice(1);
        if (text.charAt(text.length - 1) === "|") text = text.slice(0, -1);
        return text.split("|").map(function (cell) {
            return cell.trim();
        });
    }

    function renderTable(lines) {
        var headers = splitTableRow(lines[0]);
        var bodyRows = lines.slice(2).map(splitTableRow);
        var html = "<table><thead><tr>";

        headers.forEach(function (cell) {
            html += "<th>" + renderInline(cell) + "</th>";
        });

        html += "</tr></thead><tbody>";
        bodyRows.forEach(function (row) {
            html += "<tr>";
            headers.forEach(function (_, index) {
                html += "<td>" + renderInline(row[index] || "") + "</td>";
            });
            html += "</tr>";
        });
        html += "</tbody></table>";
        return html;
    }

    function renderMarkdown(input) {
        var lines = String(input == null ? "" : input).replace(/\r\n?/g, "\n").split("\n");
        var html = "";
        var i = 0;

        while (i < lines.length) {
            var line = lines[i];
            var nextLine = lines[i + 1];

            if (isBlank(line)) {
                i += 1;
                continue;
            }

            if (isFence(line)) {
                var language = line.replace(/^\s*```/, "").trim().split(/\s+/)[0] || "";
                var codeLines = [];
                i += 1;
                while (i < lines.length && !isFence(lines[i])) {
                    codeLines.push(lines[i]);
                    i += 1;
                }
                if (i < lines.length) i += 1;
                html += '<pre><code class="' + escapeAttribute(language ? "language-" + language : "") + '">' +
                    escapeHtml(codeLines.join("\n")) +
                    "</code></pre>";
                continue;
            }

            var heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/);
            if (heading) {
                var level = heading[1].length;
                html += "<h" + level + ">" + renderInline(heading[2].trim()) + "</h" + level + ">";
                i += 1;
                continue;
            }

            if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) {
                html += "<hr>";
                i += 1;
                continue;
            }

            if (/\|/.test(line) && nextLine && isTableSeparator(nextLine)) {
                var tableLines = [line, nextLine];
                i += 2;
                while (i < lines.length && /\|/.test(lines[i]) && !isBlank(lines[i])) {
                    tableLines.push(lines[i]);
                    i += 1;
                }
                html += renderTable(tableLines);
                continue;
            }

            if (/^\s{0,3}>\s?/.test(line)) {
                var quoteLines = [];
                while (i < lines.length && /^\s{0,3}>\s?/.test(lines[i])) {
                    quoteLines.push(lines[i].replace(/^\s{0,3}>\s?/, ""));
                    i += 1;
                }
                html += "<blockquote>" + renderMarkdown(quoteLines.join("\n")) + "</blockquote>";
                continue;
            }

            var unordered = line.match(/^\s*[-*+]\s+(.+)$/);
            if (unordered) {
                html += "<ul>";
                while (i < lines.length) {
                    var item = lines[i].match(/^\s*[-*+]\s+(.+)$/);
                    if (!item) break;
                    html += "<li>" + renderInline(item[1].trim()) + "</li>";
                    i += 1;
                }
                html += "</ul>";
                continue;
            }

            var ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
            if (ordered) {
                html += "<ol>";
                while (i < lines.length) {
                    var orderedItem = lines[i].match(/^\s*\d+[.)]\s+(.+)$/);
                    if (!orderedItem) break;
                    html += "<li>" + renderInline(orderedItem[1].trim()) + "</li>";
                    i += 1;
                }
                html += "</ol>";
                continue;
            }

            var paragraph = [line];
            i += 1;
            while (i < lines.length && !isBlockStart(lines[i], lines[i + 1])) {
                paragraph.push(lines[i]);
                i += 1;
            }
            html += "<p>" + renderInline(paragraph.join("\n")).replace(/\n/g, "<br>") + "</p>";
        }

        return html;
    }

    function scheduleMath(root) {
        if (typeof window.scheduleLatexRender === "function") {
            window.scheduleLatexRender(root);
        } else if (typeof window.renderLatexIn === "function") {
            window.setTimeout(function () {
                window.renderLatexIn(root);
            }, 0);
        }
    }

    function setMarkdownContent(element, text, options) {
        if (!element) return;
        var settings = options || {};
        element.classList.add(settings.inline ? "markdown-inline" : "markdown-body");
        element.innerHTML = settings.inline ? renderInline(text) : renderMarkdown(text);
        scheduleMath(element);
    }

    window.renderMarkdown = renderMarkdown;
    window.renderMarkdownInline = renderInline;
    window.setMarkdownContent = setMarkdownContent;
})();
