# SparkBot

SparkBot is an operational agent platform with a 1,500-skill registry, workflows, policy controls, NVIDIA AI integration and browser-action telemetry.

## Rodar sem instalar dependências

O comando principal agora usa somente a biblioteca padrão do Python.

Comandos:

    git clone https://github.com/carlos210609/Sparkbot.git
    cd Sparkbot
    export NVIDIA_API_KEY="nvapi-SUA_CHAVE"
    python3 sparkbot.py

Abra http://127.0.0.1:8000.

Opcional:

    export SPARKBOT_PORT=8000
    export SPARKBOT_NVIDIA_MODEL=auto

O modo auto consulta o catálogo NVIDIA e escolhe um modelo disponível da lista de preferência. Disponibilidade e preço podem mudar.

O launcher leve fornece dashboard, NVIDIA AI, SQLite, auditoria de ações do navegador e endpoints básicos, sem FastAPI/Uvicorn/Pydantic.

A aplicação FastAPI completa continua no projeto como stack avançada e pode ser usada separadamente quando as dependências forem instaladas.

Nunca coloque sua NVIDIA_API_KEY no GitHub.
