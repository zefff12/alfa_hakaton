/**
 * Кодмод: оборачивает русские строки интерфейса в t("…") и собирает список ключей.
 *   node scripts/i18n-codemod.cjs            — применить к src/ (кроме консоли банка)
 *   node scripts/i18n-codemod.cjs --keys     — только вывести ключи (для словаря)
 * Ключ перевода — сам русский текст; шаблоны `Заявка ${n}` → t("Заявка {0}", n).
 */
const fs = require("fs");
const path = require("path");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "src");
const CYR = /[А-Яа-яЁё]/;
const onlyKeys = process.argv.includes("--keys");
const files = [];
(function walk(dir) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) { if (f !== "bank") walk(p); }
    else if (/\.tsx?$/.test(f) && !/i18n/.test(f)) files.push(p);
  }
})(ROOT);

const keys = new Set();

function isTCall(node) {
  const p = node.parent;
  return p && ts.isCallExpression(p) && ts.isIdentifier(p.expression) && p.expression.text === "t";
}

for (const file of files) {
  const src = fs.readFileSync(file, "utf8");
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits = [];

  function visit(node) {
    if (ts.isImportDeclaration(node)) return;
    if (ts.isJsxText(node) && CYR.test(node.text)) {
      const raw = node.getFullText(sf);
      const m = raw.match(/^(\s*)([\s\S]*?)(\s*)$/);
      const text = m[2].replace(/\s+/g, " ");
      keys.add(text);
      const start = node.getStart(sf, true);
      edits.push([start, node.end, `${m[1]}{t(${JSON.stringify(text)})}${m[3]}`]);
      return;
    }
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && CYR.test(node.text) && !isTCall(node)) {
      const p = node.parent;
      if (ts.isPropertyAssignment(p) && p.name === node) return; // ключ объекта
      keys.add(node.text);
      const repl = ts.isJsxAttribute(p) ? `{t(${JSON.stringify(node.text)})}` : `t(${JSON.stringify(node.text)})`;
      edits.push([node.getStart(sf), node.end, repl]);
      return;
    }
    if (ts.isTemplateExpression(node) && CYR.test(node.getText(sf)) && !isTCall(node)) {
      let key = node.head.text;
      const args = [];
      node.templateSpans.forEach((span, i) => {
        args.push(span.expression.getText(sf));
        key += `{${i}}` + span.literal.text;
      });
      keys.add(key);
      edits.push([node.getStart(sf), node.end, `t(${JSON.stringify(key)}, ${args.join(", ")})`]);
      return;
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);
  if (onlyKeys || !edits.length) continue;

  let out = src;
  for (const [s, e, r] of edits.sort((a, b) => b[0] - a[0])) out = out.slice(0, s) + r + out.slice(e);
  if (!/import \{[^}]*\bt\b[^}]*\} from "[./]+i18n"/.test(out)) {
    const rel = path.relative(path.dirname(file), path.join(ROOT, "i18n")).replace(/\\/g, "/");
    const spec = rel.startsWith(".") ? rel : "./" + rel;
    const lastImport = [...out.matchAll(/^import .*;$/gm)].pop();
    const at = lastImport ? lastImport.index + lastImport[0].length : 0;
    out = out.slice(0, at) + `\nimport { t } from "${spec}";` + out.slice(at);
  }
  fs.writeFileSync(file, out);
  console.log(`${path.relative(ROOT, file)}: ${edits.length} строк`);
}

if (onlyKeys) console.log(JSON.stringify([...keys], null, 1));
else fs.writeFileSync(path.join(__dirname, "i18n-keys.json"), JSON.stringify([...keys], null, 1));
