import test from "node:test";
import assert from "node:assert/strict";

const allowed = (filePath) => {
  if (typeof filePath !== "string" || filePath.length === 0 || filePath.length > 240 || filePath.includes("\0")) return false;
  const normalized = filePath.replaceAll("\\", "/");
  if (normalized.startsWith("/") || normalized.split("/").some((part) => part === "." || part === ".." || part === "")) return false;
  return normalized === "README.md" ||
    normalized === "package.json" ||
    normalized === "package-lock.json" ||
    normalized === "tsconfig.json" ||
    normalized === "vercel.json" ||
    normalized.startsWith("src/") ||
    normalized.startsWith("tests/");
};

const validBranch = (branch) => {
  const prefix = "ralph-loop/";
  const suffix = typeof branch === "string" && branch.startsWith(prefix) ? branch.slice(prefix.length) : "";
  return /^[a-z0-9-]{6,100}$/.test(suffix);
};

test("allowlist accepts source, tests, and intended project manifests", () => {
  for (const path of ["src/server.ts", "tests/example.test.ts", "README.md", "package.json", "package-lock.json", "tsconfig.json", "vercel.json"]) {
    assert.equal(allowed(path), true, path);
  }
});

test("allowlist rejects workflows, secrets, and unrelated files", () => {
  for (const path of [".github/workflows/ralph-loop.yml", ".env", ".env.example", "../.env", "src/../package.json", "src/../../.env", "/etc/passwd", "scripts/ralph.mjs"]) {
    assert.equal(allowed(path), false, path);
  }
});

test("rejects traversal, empty segments and Windows traversal", () => {
  for (const path of ["src/./server.ts", "src//server.ts", "..\\.env", "src\\..\\package.json", ""]) {
    assert.equal(allowed(path), false, path);
  }
});

test("validates dedicated Ralph Loop branches", () => {
  for (const branch of ["ralph-loop/loop-123456-ab12cd34", "ralph-loop/fix-tests-001"]) assert.equal(validBranch(branch), true);
  for (const branch of ["main", "feature/test", "ralph-loop/../main", "ralph-loop/ABC"]) assert.equal(validBranch(branch), false);
});
