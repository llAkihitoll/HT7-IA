"""Servidor MCP de Parachute S.A. (transporte Streamable HTTP).

Centraliza las tres herramientas que usan los agentes del sistema:

    buscar_faq             -> shared.agent_tools.buscar_faq_json   (pgvector)
    consultar_clima_salto  -> shared.weather_service.describe_jump_weather (Open-Meteo)
    calendarizar_cita      -> shared.agent_tools.calendarizar_cita_json (SQLite)

Aquí no hay lógica de negocio: cada tool delega en la misma función que ya
usaban los agentes y solo agrega logs de ejecución.

Uso:

    python -m mcp_server.server        # http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Annotated

from dotenv import load_dotenv
from pydantic import Field

from mcp.server import MCPServer
from shared.agent_tools import buscar_faq_json, calendarizar_cita_json
from shared.weather_service import describe_jump_weather

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
MCP_PATH = "/mcp"
TOOL_NAMES = ("buscar_faq", "consultar_clima_salto", "calendarizar_cita")

logger = logging.getLogger("parachute.mcp")

mcp = MCPServer(
    name="parachute-tools",
    instructions=(
        "Herramientas de Parachute S.A.: evidencia de FAQs, evaluación climática "
        "del salto y registro de citas con verificación climática obligatoria."
    ),
)


@mcp.tool()
async def buscar_faq(
    pregunta: Annotated[str, Field(min_length=1, description="Pregunta del usuario en lenguaje natural.")],
) -> str:
    """Recupera evidencia de las FAQs del Lab 4; nunca inventa una respuesta."""
    return await _logged("buscar_faq", {"pregunta": pregunta}, buscar_faq_json(pregunta))


@mcp.tool()
async def consultar_clima_salto(
    fecha_iso: Annotated[str, Field(description="Fecha del salto, formato YYYY-MM-DD.")],
) -> str:
    """Consulta el clima en el sitio de aterrizaje para `fecha_iso`
    (formato YYYY-MM-DD) y determina si las condiciones permiten realizar
    el salto (ideal, marginal o prohibido), con motivos y restricciones."""
    return await _logged("consultar_clima_salto", {"fecha_iso": fecha_iso},
                         asyncio.to_thread(describe_jump_weather, fecha_iso))


@mcp.tool()
async def calendarizar_cita(
    fecha_iso: Annotated[str, Field(description="Fecha solicitada, YYYY-MM-DD.")],
    nombre_cliente: Annotated[str, Field(description="Nombre indicado por el usuario.")],
    hora: Annotated[str, Field(description="Hora acordada en Guatemala, HH:MM (24 horas).")] = "09:00",
) -> str:
    """Guarda una cita tras reconsultar clima. Marginal queda pendiente de revisión."""
    params = {"fecha_iso": fecha_iso, "hora": hora, "nombre_cliente": _mask(nombre_cliente)}
    return await _logged("calendarizar_cita", params,
                         calendarizar_cita_json(fecha_iso, nombre_cliente, hora))


async def _logged(tool: str, params: dict, call) -> str:
    """Ejecuta la tool y registra parámetros, resultado y duración."""
    logger.info("-> tool=%s params=%s", tool, params)
    started = time.perf_counter()
    try:
        result = await call
    except Exception:
        logger.exception("<- tool=%s ERROR tras %.0f ms", tool, _ms(started))
        raise
    logger.info("<- tool=%s OK resultado=%s (%.0f ms)", tool, summarize(result), _ms(started))
    return result


def summarize(result: str) -> str:
    """Resumen corto del resultado para el log (sin volcar datos completos)."""
    try:
        data = json.loads(result)
    except ValueError:
        return result.splitlines()[0] if result else "(vacío)"
    if data.get("error"):
        return f"error controlado: {data['error']}"
    if "resultados" in data:
        ids = [item.get("faq_id") for item in data["resultados"]]
        return f"{len(ids)} FAQs {ids}" if ids else "sin evidencia"
    if "estado" in data:
        return f"cita id={str(data.get('id'))[:8]} estado={data['estado']} ya_existia={data.get('ya_existia')}"
    return "ok"


def _mask(name: str) -> str:
    # El nombre del cliente es dato personal: en el log solo van las iniciales.
    return " ".join(part[0] + "." for part in name.split()) or "(vacío)"


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _warm_up_embeddings() -> None:
    # La primera carga de sentence-transformers tarda ~30 s; se hace al
    # arrancar para que la primera llamada a buscar_faq no agote timeouts.
    from shared import faqs
    from shared.faq_store.config import load_settings

    settings = load_settings()
    faqs._embedder(settings.embedding_model, settings.embedding_dimension)


def main() -> None:
    load_dotenv()
    # MCPServer ya configura el logging; se silencian las peticiones HTTP de
    # la descarga del modelo para que el log muestre solo el servidor y las tools.
    for noisy in ("httpx", "huggingface_hub", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    host = os.getenv("MCP_HOST", DEFAULT_HOST)
    port = int(os.getenv("MCP_PORT", DEFAULT_PORT))
    if os.getenv("MCP_WARMUP", "1") != "0":
        logger.info("Cargando modelo de embeddings para buscar_faq...")
        try:
            _warm_up_embeddings()
        except Exception as exc:  # el servidor sigue; buscar_faq reportará su error
            logger.warning("No se pudo precargar el modelo de embeddings: %s", exc)
    logger.info("Servidor MCP 'parachute-tools' — Streamable HTTP en http://%s:%s%s", host, port, MCP_PATH)
    logger.info("Tools expuestas: %s", ", ".join(TOOL_NAMES))
    mcp.run(transport="streamable-http", host=host, port=port, streamable_http_path=MCP_PATH)


if __name__ == "__main__":
    main()
