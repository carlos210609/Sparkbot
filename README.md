# SparkBot

Autonomous AI growth operating system for legitimate marketing, sales and growth operations.

## AI provider

SparkBot now defaults to **NVIDIA** through the NVIDIA API Catalog's OpenAI-compatible endpoint. Set `NVIDIA_API_KEY` and leave `SPARKBOT_NVIDIA_MODEL=auto` to discover an available model from the configured preference list. The key is read only from the environment and is never stored in the repository.

```bash
export NVIDIA_API_KEY="nvapi-..."
export SPARKBOT_AI_PROVIDER="nvidia"
export SPARKBOT_NVIDIA_MODEL="auto"
```

NVIDIA documents the API Catalog endpoint as `https://integrate.api.nvidia.com/v1` and exposes OpenAI-compatible chat completions and model discovery. The availability/pricing of individual models can change, so SparkBot does not falsely label a model as permanently free.

## Browser monitoring

The dashboard exposes an auditable browser-event stream at `/api/browser/events`. Actions can be recorded with action, URL, target, status and structured details. Events are persisted in SQLite and shown live in the Command Center.

This telemetry layer does not bypass authentication, CAPTCHAs, platform limits or other security controls.

## Local run

```bash
cp .env.example .env
python -m uvicorn sparkbot.app:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

## Status

Phase 1 foundation in progress.
