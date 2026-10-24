# Ralph Loop MCP

An independent MCP server that uses **ChatGPT itself as the reasoning and code-generation model**. No OpenRouter account, external model API key, or paid LLM service is required.

## What happens

1. ChatGPT reads source files using the read_files tool.
2. ChatGPT reasons about the task and generates code changes in the conversation.
3. start_loop creates a dedicated ralph-loop/* branch with those changes and dispatches GitHub Actions.
4. GitHub Actions runs npm test and npm run build. It does not call an LLM.
5. ChatGPT reads status/logs and can submit fixes using apply_changes, repeating the cycle while the conversation and client allow it.
6. Changes remain on a separate branch; the server never merges changes into main automatically.

This is a model-in-the-loop workflow, not an unattended process that runs for days without ChatGPT tool calls. Each iteration is driven by ChatGPT through MCP.

## MCP endpoint and tools

- Public endpoint: /mcp (HTTPS required)
- Health endpoint: /health
- read_files(paths, branch?)
- start_loop(task, changes)
- apply_changes(branch, task, changes, message?)
- run_checks(branch, task)
- get_status(run_id?, branch?)
- get_logs(run_id)
- stop_loop(run_id)

File writes are allowlisted to source/tests and common project manifests. GitHub workflow/security files and secret files cannot be changed by these tools.

## Vercel configuration

Configure these protected environment variables for Production and Preview:

- MCP_BEARER_TOKEN: a long random bearer secret used to authenticate the MCP client.
- GITHUB_TOKEN: a fine-grained GitHub token limited to this repository, with Contents read/write and Actions read/write permissions.

Optional variables:

- GITHUB_OWNER (default: carlos210609)
- GITHUB_REPO (default: Sparkbot)
- GITHUB_WORKFLOW_ID (default: ralph-loop.yml)

No OPENROUTER_API_KEY or other model API key is needed.

After adding or changing Vercel variables, redeploy and check /health. It should report mcpBearerToken=true and githubToken=true. Never commit tokens to the repository or share them publicly.

## Connect to ChatGPT

Use ChatGPT on the web and open Plugins, choose Add custom MCP server, and set the server URL to the public HTTPS endpoint ending in /mcp. Configure the authentication method supported by your ChatGPT workspace, review the discovered tools, then create the plugin. Tool-writing permissions and custom MCP availability depend on the ChatGPT plan and workspace policies.

## Local checks

Run npm install, npm test, and npm run build.

## Safety

The initial implementation commits to a dedicated branch and runs tests/build. It does not push code to main or auto-merge changes. Review diffs and validation results before merging.
