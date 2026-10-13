"""Alias de compatibilidad: el especialista ya usa la base real del Lab 4.

HT7: `buscar_faq` se obtiene del servidor MCP.
"""
from shared.mcp_connection import faq_mcp
from shared.specialists import make_faq_agent

faq_agent = make_faq_agent(mcp_server=faq_mcp)
