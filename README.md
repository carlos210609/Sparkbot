# Ralph Loop MCP

An independent MCP server and bounded Ralph Loop runner. This project is separate from SparkBuddy.

## Features

- MCP tools over Streamable HTTP: start a run, inspect status, inspect job/step logs, and cancel a run.
- GitHub Actions execution with a bounded cycle count.
- OpenRouter integration using a server-side Actions secret.
- Health endpoint for deployment checks.
- Bearer-token protection for the MCP endpoint.
- Tests and TypeScript build.

## Setup

Requirements: Node.js 20+, a GitHub repository with Actions enabled, a GitHub token with Actions read/write permission for the configured repository, and an OpenRouter API key.

1. Add repository secret `OPENROUTER_API_KEY`.
2. In repository Settings → Secrets and variables → Actions, add the required secrets for your deployment.
3. Run `npm install`, copy `.env.example` to `.env`, and set `MCP_BEARER_TOKEN` and `GITHUB_TOKEN`.
4. Run `npm run dev`. The MCP endpoint is `/mcp`; the health endpoint is `/health`.

## MCP tools

- `start_loop(task, cycles?)`: dispatch a workflow run.
- `get_status(run_id?)`: list recent runs or inspect one run.
- `get_logs(run_id)`: show job and step outcomes and the GitHub run URL.
- `stop_loop(run_id)`: request cancellation.

## Safety and current limitations

- The repository is fixed by environment configuration; callers cannot select arbitrary repositories.
- The MCP endpoint requires a bearer token.
- Cycles are limited to 1–3 per run.
- AI-generated changes must be reviewed before merging.
- GitHub Actions has quotas and bounded job duration. OpenRouter free model availability and quotas vary; zero cost is not guaranteed.
- This initial workflow runs the agent and uploads its progress artifact. It does not yet automatically push changes or create pull requests; those write permissions will be added only after the basic run is verified.
