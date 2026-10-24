import test from "node:test";
import assert from "node:assert/strict";

test("cycle count accepts only integers from one through three", () => {
  for (const value of [1, 2, 3]) assert.ok(Number.isInteger(value) && value >= 1 && value <= 3);
  for (const value of [0, 4, -1, NaN]) assert.ok(!(Number.isInteger(value) && value >= 1 && value <= 3));
});

test("agent path policy permits only intended source and test files", () => {
  const allowed = (path) => path === "README.md" || path.startsWith("src/") || path.startsWith("tests/");
  for (const path of ["src/server.ts", "tests/example.test.ts", "README.md"]) assert.equal(allowed(path), true);
  for (const path of [".github/workflows/ralph-loop.yml", "package.json", "../.env"]) assert.equal(allowed(path), false);
});
