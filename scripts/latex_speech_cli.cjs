#!/usr/bin/env node

const path = require("path");
const Module = require("module");

const rootDir = path.resolve(__dirname, "..");
const frontendNodeModules = path.join(rootDir, "frontend", "node_modules");
process.env.NODE_PATH = [frontendNodeModules, process.env.NODE_PATH].filter(Boolean).join(path.delimiter);
Module._initPaths();

require("mathjax-full/js/input/tex/base/BaseConfiguration.js");
require("mathjax-full/js/input/tex/ams/AmsConfiguration.js");
require("mathjax-full/js/input/tex/newcommand/NewcommandConfiguration.js");
require("mathjax-full/js/input/tex/boldsymbol/BoldsymbolConfiguration.js");
require("mathjax-full/js/input/tex/mathtools/MathtoolsConfiguration.js");
require("mathjax-full/js/input/tex/physics/PhysicsConfiguration.js");
require("mathjax-full/js/input/tex/cancel/CancelConfiguration.js");
require("mathjax-full/js/input/tex/color/ColorConfiguration.js");
require("mathjax-full/js/input/tex/html/HtmlConfiguration.js");
require("mathjax-full/js/input/tex/mhchem/MhchemConfiguration.js");

const { mathjax } = require("mathjax-full/js/mathjax.js");
const { TeX } = require("mathjax-full/js/input/tex.js");
const { liteAdaptor } = require("mathjax-full/js/adaptors/liteAdaptor.js");
const { RegisterHTMLHandler } = require("mathjax-full/js/handlers/html.js");
const { SerializedMmlVisitor } = require("mathjax-full/js/core/MmlTree/SerializedMmlVisitor.js");
const sre = require("speech-rule-engine");

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function createMathJax() {
  const adaptor = liteAdaptor();
  RegisterHTMLHandler(adaptor);
  const tex = new TeX({
    packages: [
      "base",
      "ams",
      "newcommand",
      "boldsymbol",
      "mathtools",
      "physics",
      "cancel",
      "color",
      "html",
      "mhchem",
    ],
  });
  const document = mathjax.document("", { InputJax: tex });
  const visitor = new SerializedMmlVisitor();
  return { document, visitor };
}

function latexToMathml(context, latex, display) {
  const root = context.document.convert(latex, { display: Boolean(display) });
  return context.visitor.visitTree(root, context.document);
}

async function main() {
  const raw = await readStdin();
  const payload = raw.trim() ? JSON.parse(raw) : {};
  const formulas = Array.isArray(payload.formulas) ? payload.formulas : [];
  const domain = payload.domain || "mathspeak";
  const style = payload.style || "default";

  await sre.setupEngine({
    locale: "en",
    domain,
    style,
    modality: "speech",
    markup: "none",
  });

  const context = createMathJax();
  const results = formulas.map((item) => {
    const id = item && item.id !== undefined ? item.id : null;
    const latex = String((item && item.latex) || "");
    try {
      if (!latex.trim()) {
        return { id, ok: false, error: "empty formula" };
      }
      const mathml = latexToMathml(context, latex, item && item.display);
      const speech = sre.toSpeech(mathml).replace(/\s+/g, " ").trim();
      return { id, ok: Boolean(speech), speech, mathml };
    } catch (error) {
      return { id, ok: false, error: error && error.message ? error.message : String(error) };
    }
  });

  process.stdout.write(JSON.stringify({ ok: true, engine: "mathjax-sre", results }));
}

main().catch((error) => {
  process.stdout.write(
    JSON.stringify({
      ok: false,
      engine: "mathjax-sre",
      error: error && error.message ? error.message : String(error),
    })
  );
  process.exitCode = 1;
});
