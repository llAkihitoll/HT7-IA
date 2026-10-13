"""Clientes MCP (Streamable HTTP) que usan los agentes jerárquicos.

Todos apuntan al mismo servidor `mcp_server` (MCP_SERVER_URL). Cada agente
recibe su propio cliente filtrado a su herramienta, así ninguno obtiene tools
que antes no tenía: Clima -> consultar_clima_salto, FAQs -> buscar_faq,
Reservas -> calendarizar_cita.

Antes de ejecutar los agentes hay que abrir las conexiones:

    async with connect_mcp_clients():
        await Runner.run(supervisor, ...)
"""

from __future__ import annotations

import os
from contextlib import AsyncExitStack, asynccontextmanager

from dotenv import load_dotenv

from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter

load_dotenv()

DEFAULT_MCP_SERVER_URL = "http://127.0.0.1:8001/mcp"
# calendarizar_cita consulta Open-Meteo (hasta 10 s) y escribe en SQLite;
# el valor por defecto del SDK (5 s) es demasiado corto.
TOOL_TIMEOUT_SECONDS = 60


def mcp_server_url() -> str:
    return os.getenv("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)


def make_mcp_client(name: str, tool_name: str, url: str | None = None) -> MCPServerStreamableHttp:
    return MCPServerStreamableHttp(
        params={"url": url or mcp_server_url(), "timeout": 30, "sse_read_timeout": 300},
        name=name,
        cache_tools_list=True,
        client_session_timeout_seconds=TOOL_TIMEOUT_SECONDS,
        tool_filter=create_static_tool_filter(allowed_tool_names=[tool_name]),
    )


faq_mcp = make_mcp_client("mcp-faqs", "buscar_faq")
weather_mcp = make_mcp_client("mcp-clima", "consultar_clima_salto")
booking_mcp = make_mcp_client("mcp-reservas", "calendarizar_cita")
MCP_CLIENTS = (faq_mcp, weather_mcp, booking_mcp)


@asynccontextmanager
async def connect_mcp_clients(clients=MCP_CLIENTS):
    """Conecta los clientes al servidor MCP y los cierra al terminar."""
    async with AsyncExitStack() as stack:
        for client in clients:
            await stack.enter_async_context(client)
        yield clients
