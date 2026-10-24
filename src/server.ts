import "dotenv/config";
import express, { type Request, type Response, type NextFunction } from "express";
import { timingSafeEqual } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "1mb" }));

const owner = process.env.GITHUB_OWNER ?? "carlos210609";
const repo = process.env.GITHUB_REPO ?? "Sparkbot";
const workflowId = process.env.GITHUB_WORKFLOW_ID ?? "ralph-loop.yml";
const githubToken = process.env.GITHUB_TOKEN;
const bearerToken = process.env.MCP_BEARER_TOKEN;
const port = Number.parseInt(process.env.PORT ?? "3000", 10);

function authenticate(req: Request, res: Response, next: NextFunction) {
  const supplied = req.header("authorization")?.replace(/^Bearer\s+/i, "") ?? "";
  if (!bearerToken) return res.status(503).json({ error: "MCP_BEARER_TOKEN is not configured" });
  const a = Buffer.from(supplied);
  const b = Buffer.from(bearerToken);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return res.status(401).json({ error: "Unauthorized" });
  next();
}

async function github(path: string, init: RequestInit = {}) {
  if (!githubToken) throw new Error("GITHUB_TOKEN is not configured on the MCP server.");
  const response = await fetch(`https://api.github.com/repos/${owner}/${repo}${path}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${githubToken}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
      ...init.headers
    }
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`GitHub API ${response.status}: ${body.slice(0, 800)}`);
  return body ? JSON.parse(body) as any : {};
}

function createServer() {
  const server = new McpServer({ name: "ralph-loop-mcp", version: "0.1.0" });

  server.registerTool("start_loop", {
    title: "Start Ralph Loop",
    description: "Dispatch a bounded AI engineering run to GitHub Actions. The workflow exports proposed changes as an artifact for manual review; it does not push or merge code.",
    inputSchema: {
      task: z.string().trim().min(8).max(2000),
      cycles: z.number().int().min(1).max(3).optional()
    }
  }, async ({ task, cycles }) => {
    const selectedCycles = cycles ?? 1;
    await github(`/actions/workflows/${encodeURIComponent(workflowId)}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: "main", inputs: { task, cycles: String(selectedCycles) } })
    });
    return { content: [{ type: "text", text: JSON.stringify({
      accepted: true, repository: `${owner}/${repo}`, workflow: workflowId,
      task, cycles: selectedCycles, message: "Dispatch accepted. Check get_status in a few seconds."
    }, null, 2) }] };
  });

  server.registerTool("get_status", {
    title: "Get Ralph Loop Status",
    description: "List recent workflow runs or inspect a specific run ID.",
    inputSchema: { run_id: z.number().int().positive().optional() }
  }, async ({ run_id }) => {
    const result = run_id
      ? await github(`/actions/runs/${run_id}`)
      : await github(`/actions/workflows/${encodeURIComponent(workflowId)}/runs?per_page=5`);
    const simplify = (run: any) => ({
      id: run.id, name: run.name, title: run.display_title,
      status: run.status, conclusion: run.conclusion,
      branch: run.head_branch, created_at: run.created_at,
      html_url: run.html_url
    });
    const value = Array.isArray(result.workflow_runs) ? result.workflow_runs.map(simplify) : simplify(result);
    return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
  });

  server.registerTool("get_logs", {
    title: "Get Ralph Loop Logs",
    description: "Show job and step statuses for a run, with a link to full GitHub logs.",
    inputSchema: { run_id: z.number().int().positive() }
  }, async ({ run_id }) => {
    const [run, jobs] = await Promise.all([
      github(`/actions/runs/${run_id}`),
      github(`/actions/runs/${run_id}/jobs?per_page=50`)
    ]);
    return { content: [{ type: "text", text: JSON.stringify({
      run: { id: run.id, status: run.status, conclusion: run.conclusion, html_url: run.html_url },
      jobs: (jobs.jobs ?? []).map((job: any) => ({
        name: job.name, status: job.status, conclusion: job.conclusion,
        steps: (job.steps ?? []).map((step: any) => ({
          name: step.name, status: step.status, conclusion: step.conclusion
        }))
      }))
    }, null, 2) }] };
  });

  server.registerTool("stop_loop", {
    title: "Stop Ralph Loop",
    description: "Request cancellation of an in-progress GitHub Actions run.",
    inputSchema: { run_id: z.number().int().positive() }
  }, async ({ run_id }) => {
    await github(`/actions/runs/${run_id}/cancel`, { method: "POST" });
    return { content: [{ type: "text", text: JSON.stringify({ accepted: true, run_id, status: "cancellation_requested" }) }] };
  });

  return server;
}

app.get("/health", (_req, res) => res.json({
  ok: true, service: "ralph-loop-mcp", repository: `${owner}/${repo}`,
  configured: { githubToken: Boolean(githubToken), bearerToken: Boolean(bearerToken) }
}));

app.all("/mcp", authenticate, async (req, res) => {
  const server = createServer();
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  res.on("close", () => { void transport.close(); void server.close(); });
  try {
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  } catch (error) {
    console.error("MCP request failed:", error);
    if (!res.headersSent) res.status(500).json({ error: "MCP request failed" });
  }
});

app.listen(port, "0.0.0.0", () => console.log(`Ralph Loop MCP listening on port ${port}`));
