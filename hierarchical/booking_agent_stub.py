"""Alias de compatibilidad: reservas persistentes con comprobación climática.

HT7: `calendarizar_cita` se obtiene del servidor MCP.
"""
from shared.mcp_connection import booking_mcp
from shared.specialists import make_booking_agent

booking_agent = make_booking_agent(mcp_server=booking_mcp)
