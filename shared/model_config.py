"""Modelo con el que corre el sistema jerárquico.

Mismo esquema que `evals/provider.py` de HT6: el modelo se inyecta con
`RunConfig` y el SDK lo propaga a los sub-agentes expuestos con `as_tool`.

- Con NVIDIA_API_KEY: NVIDIA NIM (compatible con OpenAI, chat completions).
- Si no, con OPENAI_API_KEY: OpenAI con el modelo de OPENAI_MODEL o el del SDK.
"""

import os

from agents import RunConfig
from agents.models.openai_provider import OpenAIProvider

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "openai/gpt-oss-20b"
PLACEHOLDER_KEY = "sk-your-key-here"


class ModelConfigError(RuntimeError):
    pass


def build_run_config() -> RunConfig:
    nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if nvidia_key:
        return RunConfig(
            model_provider=OpenAIProvider(
                api_key=nvidia_key,
                base_url=os.getenv("NVIDIA_BASE_URL", NVIDIA_BASE_URL),
                use_responses=False,
            ),
            model=os.getenv("AGENT_MODEL", "").strip() or NVIDIA_DEFAULT_MODEL,
            # Sin clave de OpenAI el exportador de trazas solo emitiría avisos.
            tracing_disabled=True,
        )
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and openai_key != PLACEHOLDER_KEY:
        return RunConfig(model=os.getenv("OPENAI_MODEL") or None)
    raise ModelConfigError(
        "Falta NVIDIA_API_KEY u OPENAI_API_KEY. Copia .env.example a .env y configura una."
    )


def describe_model(run_config: RunConfig) -> str:
    return str(run_config.model or "modelo predeterminado del SDK")
