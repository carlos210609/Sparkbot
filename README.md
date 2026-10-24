# SladeGPT MCP

A single-owner MCP server that uses **ChatGPT itself as the reasoning and code-generation model**. No OpenRouter account, external model API key, or GitHub personal access token is required.

## Tokenless workflow

1. ChatGPT reads allowlisted source files from the public repository.
2. ChatGPT reasons about the task and authors complete file replacements.
3. SladeGPT returns a patch artifact containing the proposed files.
4. Apply those file replacements in your repository and run `npm test` and `npm run build` in your own checkout or CI.
5. Ask ChatGPT to inspect failures and prepare another patch iteration.

**Important limitation:** without GitHub credentials, this service cannot commit to GitHub, create branches, trigger GitHub Actions, or read private workflow logs. It does not claim that a patch has been committed or tested remotely.

## MCP endpoints and OAuth

- MCP endpoint: https://ralph-loop-mcp-independent.vercel.app/mcp
- Health: /health
- Protected Resource Metadata for `/mcp`: `/.well-known/oauth-protected-resource/mcp`
- Origin-level Protected Resource Metadata: `/.well-known/oauth-protected-resource`
- OAuth Authorization Server Metadata: /.well-known/oauth-authorization-server
- OAuth client registration: /oauth/register
- OAuth authorization: /oauth/authorize
- OAuth token: /oauth/token

The server implements a minimal OAuth 2.1 authorization-code flow with PKCE S256, refresh tokens, resource metadata, and dynamic client registration. It uses a single-owner password for personal use; it is not a multi-user identity provider or an enterprise SSO service. Keep the password private and rotate it if exposed.

## MCP tools

- `read_files(paths, branch?)`
- `start_loop(task, changes)` — returns a tokenless patch artifact
- `apply_changes(branch, task, changes, message?)` — returns the next patch artifact
- `run_checks(branch, task)` — provides local test commands, does not run them
- `get_status(run_id?, branch?)` — explains tokenless execution status
- `get_logs(run_id)` — provides local validation commands
- `stop_loop(run_id)` — reports that no remote run is managed

Repository reads and proposed file replacements are limited to source/tests and common project manifests. Workflow/security files and secret files cannot be changed through these tools.

## Vercel environment variables

Required for OAuth:
- `OAUTH_SIGNING_SECRET`: random secret of at least 32 characters used to sign OAuth clients, codes and tokens.
- `MCP_USER_PASSWORD`: strong, private password used at the OAuth consent/login page.
- `PUBLIC_BASE_URL`: `https://ralph-loop-mcp-independent.vercel.app`

**Not required:** `GITHUB_TOKEN`, `OPENROUTER_API_KEY`, or any external model API key.

After changing environment variables, redeploy and check `/health`. Never commit or publicly share credentials.

## Connect to ChatGPT

Use ChatGPT on the web, choose Plugins > Add custom MCP server, and enter the public HTTPS MCP endpoint. Select OAuth when asked for authentication, authorize using the MCP user password configured above, then scan/create the plugin. Custom MCP capabilities depend on ChatGPT plan and workspace permissions.

## Local validation

Run `npm ci`, `npm test`, and `npm run build`.

## Safety

SladeGPT returns proposed changes as artifacts; it does not commit to `main`, create remote branches, dispatch workflows, or claim tests passed. Review and validate all changes before applying them.
