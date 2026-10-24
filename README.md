# Ralph Loop MCP

An independent MCP server for controlling a bounded Ralph Loop via ChatGPT-compatible MCP clients. This project is separate from SparkBuddy.

## Endpoints

- `/mcp`: MCP Streamable HTTP endpoint (Bearer-token protected)
- `/health`: deployment/configuration health check (does not reveal secrets)

## MCP tools

- `start_loop(task, cycles?)`: dispatch the `Ralph Loop` GitHub Actions workflow. Cycles are limited to 1–3.
- `get_status(run_id?)`: list recent workflow runs or inspect one run.
- `get_logs(run_id)`: retrieve job and step outcomes plus full-log URL.
- `stop_loop(run_id)`: request cancellation of an in-progress workflow.

## Deployment on Vercel

This repo includes Vercel Node.js function entry points and rewrites for stable `/mcp` and `/health` URLs.

Set these encrypted/sensitive Vercel environment variables for Preview and Production:
- `MCP_BEARER_TOKEN`: long random secret used for HTTP Bearer authentication.
- `GITHUB_TOKEN`: fine-grained GitHub token scoped only to this repository, with Actions read/write. Read access to workflow runs/jobs and workflow dispatch/cancel requires Actions read/write.

Set this GitHub Actions repository secret:
- `OPENROUTER_API_KEY`: API key for an available model. Provider free quotas and model availability vary, so $0 usage is not guaranteed.

Optional Vercel variables:
- `GITHUB_OWNER` (default `carlos210609`)
- `GITHUB_REPO` (default `Sparkbot`)
- `GITHUB_WORKFLOW_ID` (default `ralph-loop.yml`)

After adding variables, redeploy. Check `/health`; it should show `mcpBearerToken: true` and `githubToken: true`. Never put tokens in source files or client-side code.

## Local development

```bash
npm install
cp .env.example .env
npm run dev
```

The production host uses the Vercel functions in `api/`. For Vercel deployment, test the public `/mcp` endpoint with MCP Inspector. Requests must include `Authorization: Bearer <MCP_BEARER_TOKEN>`.

## Safety

The workflow has a bounded number of cycles and execution time. It exports a proposed patch artifact for review; this first version does not automatically push or merge AI-authored changes. Review all generated output before applying it.
