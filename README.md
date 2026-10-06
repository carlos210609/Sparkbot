# SparkBot

SparkBot is an agent runtime with 1,500 operational skill slots, a 700-profile specialist mesh, mission control, persistent telemetry, NVIDIA AI, public web search/fetch and an optional real Chromium browser.

## Quick start

    git clone https://github.com/carlos210609/Sparkbot.git
    cd Sparkbot
    export NVIDIA_API_KEY="nvapi-SUA_CHAVE"
    python3 sparkbot.py

Open http://127.0.0.1:8000.

The launcher is intentionally lightweight and does not require FastAPI/Uvicorn for the command center.

## NVIDIA

SparkBot uses NVIDIA hosted chat completions by default at https://integrate.api.nvidia.com/v1/chat/completions. The default model is openai/gpt-oss-20b. NVIDIA documents this model as supporting agentic tool use.

Override the model with SPARKBOT_NVIDIA_MODEL if needed. Never commit NVIDIA_API_KEY.

## Real browser agent

The browser runtime is optional because Chromium is a separate dependency.

    python3 -m pip install -e ".[browser]"
    python3 -m playwright install chromium
    python3 sparkbot.py

The Browser Monitor shows whether Playwright/Chromium is available. The browser supports public navigation, clicks, form filling, visible-text inspection and screenshots. Actions are audited. It does not bypass CAPTCHA, authentication, platform limits or security controls.

Browser profile data is stored under .sparkbot-browser by default. Keep that directory private.

## Agent capabilities

- web_search — public web search
- web_fetch — public web retrieval
- browser_navigate / browser_click / browser_fill / browser_text / browser_screenshot
- persistent SQLite missions, memory and audit events
- 700 specialist agent profiles
- 1,500 skill slots
- permission and verification engine

The model is instructed to reason as an agent, but the runtime remains authoritative: SparkBot must not claim an action occurred without tool evidence.

## Development

    python3 -m pip install -e ".[dev]"
    python3 -m compileall -q sparkbot.py sparkbot
    python3 -m pytest -q
    ruff check .

If GitHub Actions is enabled for the repository, the same checks run on push and pull request.
