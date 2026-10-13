"""Agente de Clima — Integrante 2 (arquitectura jerárquica).

Obtiene y evalúa datos reales mediante el servicio compartido de Open-Meteo.
No decide reservas ni responde FAQs.

HT7: la herramienta `consultar_clima_salto` vive en el servidor MCP
(`mcp_server/server.py`), que delega en `shared.weather_service`.
"""

from agents import Agent

from shared.mcp_connection import weather_mcp

weather_agent = Agent(
    name="Agente Clima",
    handoff_description=(
        "Consulta las condiciones climáticas del sitio de aterrizaje para una "
        "fecha y determina si el salto es ideal, marginal o está prohibido."
    ),
    instructions=(
        "Eres el agente climático de Parachute S.A. Usa consultar_clima_salto "
        "con la fecha solicitada por el usuario (formato YYYY-MM-DD) y reporta "
        "el estado, los motivos y las restricciones tal como te los devuelve "
        "la herramienta, sin inventar información adicional."
    ),
    mcp_servers=[weather_mcp],
)
