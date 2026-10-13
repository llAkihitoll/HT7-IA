"""Programa de demostración — Arquitectura jerárquica (Integrante 2, HT5).

Ejecuta el flujo completo de la jerarquía:

    Usuario -> Supervisor General -> [Agente FAQs | Submanager Operaciones]
                                            -> [Agente Clima | Agente Reservas]

usando el SDK de OpenAI Agents (`Runner` + `Agent.as_tool()`). En HT7 las
herramientas de los especialistas se ejecutan en el servidor MCP, que debe
estar levantado (`python -m mcp_server.server`). Requiere NVIDIA_API_KEY u
OPENAI_API_KEY (ver `.env.example`).
"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from agents import Runner  # noqa: E402

from hierarchical.supervisor import supervisor  # noqa: E402
from shared.mcp_connection import connect_mcp_clients, mcp_server_url  # noqa: E402
from shared.model_config import ModelConfigError, build_run_config  # noqa: E402

# Fecha relativa a hoy para quedar dentro del horizonte de 16 días.
DEMO_DATE = (datetime.now(ZoneInfo("America/Guatemala")).date() + timedelta(days=3)).isoformat()

DEMO_QUERIES = [
    ("FAQs", "¿Cuál es la edad mínima para poder hacer el salto en tándem?"),
    (
        "Clima (dentro del horizonte de 16 días)",
        f"¿Las condiciones climáticas permiten saltar el {DEMO_DATE}?",
    ),
    (
        "Reservas (consulta clima antes de calendarizar)",
        f"Quiero calendarizar una cita de salto para el {DEMO_DATE}, a las 09:00, mi nombre es Juana Pérez.",
    ),
    (
        "Clima (fuera del horizonte de pronóstico de Open-Meteo)",
        "¿Puedo saltar el 2027-01-01?",
    ),
]


async def run_demo() -> None:
    try:
        run_config = build_run_config()
    except ModelConfigError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Conectando al servidor MCP en {mcp_server_url()} ...")
    async with connect_mcp_clients():
        for titulo, mensaje in DEMO_QUERIES:
            print("=" * 80)
            print(f"[{titulo}]")
            print(f"Usuario: {mensaje}")
            print("-" * 80)
            result = await Runner.run(supervisor, mensaje, run_config=run_config)
            print(f"Supervisor General: {result.final_output}")
            print()


if __name__ == "__main__":
    asyncio.run(run_demo())
