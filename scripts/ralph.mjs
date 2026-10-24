import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve, relative, sep, isAbsolute } from "node:path";

const task = process.env.RALPH_TASK?.trim();
const cycles = Number.parseInt(process.env.RALPH_CYCLES ?? "1", 10);
const apiKey = process.env.OPENROUTER_API_KEY;
const model = process.env.RALPH_MODEL || "openrouter/auto";
const progressPath = ".ralph/progress.md";
const repoRoot = resolve(".");

if (!task || task.length < 8 || task.length > 2000) throw new Error("RALPH_TASK must be 8-2000 characters.");
if (!Number.isInteger(cycles) || cycles < 1 || cycles > 3) throw new Error("RALPH_CYCLES must be between 1 and 3.");
if (!apiKey) throw new Error("Missing OPENROUTER_API_KEY GitHub Actions secret.");

const run = (cmd, args) => execFileSync(cmd, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
const log = (message) => {
  mkdirSync(dirname(progressPath), { recursive: true });
  const old = (() => { try { return readFileSync(progressPath, "utf8"); } catch { return "# Ralph Progress\n"; } })();
  writeFileSync(progressPath, old + `\n- ${new Date().toISOString()} — ${message}\n`);
  console.log(message);
};

// Resolve and validate normalized paths; checking only the original prefix would allow
// values such as "src/../package.json" to escape the intended write allowlist.
const allowed = (filePath) => {
  if (typeof filePath !== "string" || filePath.length === 0 || filePath.includes("\0")) return false;
  const normalized = filePath.replaceAll("\\", "/");
  if (normalized.startsWith("/") || normalized.split("/").some((part) => part === "." || part === "..")) return false;
  const target = resolve(repoRoot, normalized);
  const rel = relative(repoRoot, target).split(sep).join("/");
  if (isAbsolute(rel) || rel === ".." || rel.startsWith("../")) return false;
  return rel === "README.md" || rel.startsWith("src/") || rel.startsWith("tests/");
};

const readContext = () => {
  const paths = run("git", ["ls-files"]).split("\n").filter(Boolean).filter(allowed).slice(0, 35);
  let size = 0;
  const files = [];
  for (const path of paths) {
    try {
      const content = readFileSync(path, "utf8");
      if (content.length > 12000 || size + content.length > 50000) continue;
      size += content.length;
      files.push(`\n--- FILE: ${path} ---\n${content}`);
    } catch {}
  }
  return files.join("\n");
};

async function askModel(prompt) {
  const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://github.com/carlos210609/Sparkbot",
      "X-Title": "Ralph Loop MCP"
    },
    body: JSON.stringify({
      model, temperature: 0.2,
      messages: [
        { role: "system", content: 'You are a careful software engineer in a bounded loop. Return ONLY JSON: {"summary":"...","files":[{"path":"src/file.ts","content":"complete file contents"}],"done":false}. Only write complete text files under src/, tests/, or README.md. Never modify workflows, package manifests, secrets, deployment settings, or permissions. Make small, testable changes. If no safe change is justified, return files: [] and explain why.' },
        { role: "user", content: prompt }
      ]
    })
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`OpenRouter API ${response.status}: ${body.slice(0, 1200)}`);
  const data = JSON.parse(body);
  const text = data.choices?.[0]?.message?.content;
  if (typeof text !== "string") throw new Error("Model returned no text content.");
  try { return JSON.parse(text); }
  catch {
    const match = text.match(/\{[\s\S]*\}/);
    if (match) return JSON.parse(match[0]);
    throw new Error("Model did not return valid JSON.");
  }
}

log(`Starting task; cycles=${cycles}; model=${model}`);
for (let cycle = 1; cycle <= cycles; cycle++) {
  const context = readContext();
  const progress = (() => { try { return readFileSync(progressPath, "utf8"); } catch { return ""; } })();
  const prompt = `TASK / ACCEPTANCE CRITERIA:\n${task}\n\nCYCLE ${cycle} OF ${cycles}\n\nPROGRESS:\n${progress.slice(-8000)}\n\nCURRENT FILES:\n${context}\n\nMake the smallest useful improvement. Return JSON only. If acceptance criteria are met, return files: [] and done: true. Do not claim tests passed without evidence.`;
  const result = await askModel(prompt);
  if (!result || typeof result.summary !== "string" || !Array.isArray(result.files)) throw new Error("Invalid model response schema.");
  let changed = 0;
  for (const file of result.files) {
    if (!file || typeof file.path !== "string" || typeof file.content !== "string" || !allowed(file.path)) {
      throw new Error("Rejected invalid path/content; writes are limited to src/, tests/, and README.md without traversal.");
    }
    const target = resolve(repoRoot, file.path.replaceAll("\\", "/"));
    const rel = relative(repoRoot, target);
    if (isAbsolute(rel) || rel === ".." || rel.startsWith(`..${sep}`)) throw new Error("Path traversal rejected.");
    if (file.content.length > 100000) throw new Error(`File too large: ${file.path}`);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, file.content);
    changed++;
  }
  log(`Cycle ${cycle}: ${result.summary}; files changed=${changed}`);
  if (changed > 0) {
    try { run("npm", ["test"]); log("npm test passed"); }
    catch (error) { log(`npm test failed: ${String(error?.stderr ?? error?.stdout ?? error).slice(-2000)}`); }
  }
  if (result.done === true || changed === 0) {
    log(result.done === true ? "Model reported task complete." : "No changes proposed; stopping to avoid a no-op loop.");
    break;
  }
}
log("Execution finished. Review the proposed patch artifact before applying changes.");
