import type { IncomingMessage, ServerResponse } from "node:http";

export default function handler(_req: IncomingMessage, res: ServerResponse): void {
  res.statusCode = 200;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify({
    ok: true,
    service: "ralph-loop-mcp",
    repository: `${process.env.GITHUB_OWNER ?? "carlos210609"}/${process.env.GITHUB_REPO ?? "Sparkbot"}`,
    configured: {
      mcpBearerToken: Boolean(process.env.MCP_BEARER_TOKEN),
      githubToken: Boolean(process.env.GITHUB_TOKEN),
      workflowSecretRequired: "OPENROUTER_API_KEY must be configured in GitHub Actions"
    }
  }));
}
