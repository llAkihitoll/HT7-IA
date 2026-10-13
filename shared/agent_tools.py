"""Herramientas comunes para los tres estilos de orquestación.

Las funciones `*_json` contienen la lógica de cada herramienta. Se exponen
como `function_tool` local (centralizada y descentralizada) y como tools del
servidor MCP (`mcp_server/server.py`), sin duplicar su implementación.
"""

import asyncio
import json
import logging
import sqlite3

from agents import function_tool

from shared import faqs, bookings
from shared.open_meteo_client import WeatherProviderError

logger = logging.getLogger(__name__)


def encode(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


async def buscar_faq_json(pregunta: str) -> str:
    """Recupera evidencia de las FAQs del Lab 4; nunca inventa una respuesta."""
    try:
        results = await asyncio.to_thread(faqs.search_faqs, pregunta)
        return encode({"resultados": results, "sin_evidencia": not results})
    except Exception:
        logger.warning("Consulta de FAQs no disponible; revisa configuración y base local.")
        return encode({"error": "No se pudo consultar la base de FAQs. Verifica PostgreSQL y la carga del corpus.",
                       "resultados": []})


async def calendarizar_cita_json(fecha_iso: str, nombre_cliente: str, hora: str = "09:00") -> str:
    """Guarda una cita tras reconsultar clima. Marginal queda pendiente de revisión.

    Args:
        fecha_iso: Fecha solicitada, YYYY-MM-DD.
        nombre_cliente: Nombre indicado por el usuario.
        hora: Hora acordada con el usuario en Guatemala, HH:MM (24 horas).
    """
    try:
        result = await asyncio.to_thread(bookings.create_booking, fecha_iso, nombre_cliente, hora)
        return encode(result)
    except (bookings.BookingError, WeatherProviderError) as exc:
        return encode({"error": str(exc), "registrada": False})
    except (sqlite3.Error, OSError):
        return encode({"error": "No fue posible guardar la cita. Intenta nuevamente.", "registrada": False})


buscar_faq = function_tool(buscar_faq_json, name_override="buscar_faq")
calendarizar_cita = function_tool(calendarizar_cita_json, name_override="calendarizar_cita")
