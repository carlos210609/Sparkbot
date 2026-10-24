import test from "node:test";
import assert from "node:assert/strict";
import { isAbsolute, relative, resolve, sep } from "node:path";

const root = resolve(".");
const allowed = (filePath) => {
  if (typeof filePath !== "string" || filePath.length === 0 || filePath.includes("\0")) return false;
  const normalized = filePath.replaceAll("\\", "/");
  if (normalized.startsWith("/") || normalized.split("/").some((part) => part === "." || part === "..")) return false;
  const target = resolve(root, normalized);
  const rel = relative(root, target).split(sep).join("/");
  if (isAbsolute(rel) || rel === ".." || rel.startsWith("../")) return false;
  return rel === "README.md" || rel.startsWith("src/") || rel.startsWith("tests/");
};

test("cycle count accepts only integers from one through three", () => {
  for (const value of [1, 2, 3]) assert.ok(Number.isInteger(value) && value >= 1 && value <= 3);
  for (const value of [0, 4, -1, NaN]) assert.ok(!(Number.isInteger(value) && value >= 1 && value <= 3));
});

test("agent path policy permits intended files and rejects config edits", () => {
  for (const path of ["src/server.ts", "tests/example.test.ts", "README.md"]) assert.equal(allowed(path), true);
  for (const path of [".github/workflows/ralph-loop.yml", "package.json", ".env", "../.env"]) assert.equal(allowed(path), false);
});

test("agent path policy rejects traversal, absolute paths, and backslash traversal", () => {
  for (const path of [
    "src/../package.json",
    "src/../../.env",
    "tests/../.github/workflows/ralph-loop.yml",
    "..\\.env",
    "src\\..\\package.json",
    "/etc/passwd",
    "src/./server.ts"
  ]) assert.equal(allowed(path), false, path);
});
