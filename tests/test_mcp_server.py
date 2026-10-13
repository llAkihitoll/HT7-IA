"""Servidor MCP real sobre Streamable HTTP, consultado con el cliente MCP del SDK.

El servidor corre con uvicorn en un puerto local. Solo se reemplazan las
fronteras externas (Open-Meteo y pgvector), igual que en las otras pruebas.
"""
import asyncio
import json
import logging
import socket
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
import uvicorn
from agents import RunConfig, Runner
from agents.mcp import MCPServerStreamableHttp

from hierarchical.weather_agent import weather_agent
from mcp_server.server import TOOL_NAMES, mcp
from shared import bookings, faqs, weather_service
from shared.mcp_connection import make_mcp_client
from shared.weather_contracts import WeatherReading
from test_decentralized import ScriptedModel

IDEAL = WeatherReading(10, 20, 0, 10, 24)
MARGINAL = WeatherReading(20, 35, 0, 10, 24)
LLUVIA = WeatherReading(10, 20, 0.1, 10, 24)


def future_date(days=1):
    return (datetime.now(ZoneInfo("America/Guatemala")).date() + timedelta(days=days)).isoformat()


@pytest.fixture(scope="module")
def mcp_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mcp.streamable_http_app(), host="127.0.0.1",
                                           port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        assert time.monotonic() < deadline, "El servidor MCP no arrancó"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=5)


def call_tool(url, name, arguments):
    async def run():
        async with MCPServerStreamableHttp(params={"url": url}, client_session_timeout_seconds=30) as client:
            return await client.call_tool(name, arguments)
    return asyncio.run(run())


def text_of(result):
    return result.content[0].text


def is_error(result):
    return bool(result.is_error)


def test_server_lists_the_three_system_tools_with_schemas(mcp_url):
    async def run():
        async with MCPServerStreamableHttp(params={"url": mcp_url}) as client:
            return await client.list_tools()
    tools = {tool.name: tool for tool in asyncio.run(run())}

    assert set(tools) == set(TOOL_NAMES)
    booking_schema = tools["calendarizar_cita"].input_schema
    assert set(booking_schema["required"]) == {"fecha_iso", "nombre_cliente"}
    assert booking_schema["properties"]["hora"]["default"] == "09:00"
    assert tools["buscar_faq"].input_schema["required"] == ["pregunta"]
    assert tools["consultar_clima_salto"].input_schema["required"] == ["fecha_iso"]
    assert all(tool.description for tool in tools.values())


def test_transport_is_streamable_http(mcp_url):
    # Un único endpoint HTTP: POST JSON-RPC que responde con JSON o SSE y
    # asigna una sesión con el encabezado Mcp-Session-Id.
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"}}}
    response = httpx.post(mcp_url, json=initialize, timeout=10, headers={
        "Accept": "application/json, text/event-stream"})

    assert response.status_code == 200
    assert response.headers.get("mcp-session-id")
    assert response.headers["content-type"].split(";")[0] in {"text/event-stream", "application/json"}
    assert "parachute-tools" in response.text


def test_weather_tool_returns_existing_evaluation(mcp_url, monkeypatch):
    monkeypatch.setattr(weather_service, "get_weather_reading", lambda _: (MARGINAL, None))
    fecha = future_date()

    result = call_tool(mcp_url, "consultar_clima_salto", {"fecha_iso": fecha})

    assert not is_error(result)
    # Mismo texto que produce el servicio compartido usado antes por el agente.
    assert text_of(result) == weather_service.describe_jump_weather(fecha)
    assert "MARGINAL" in text_of(result)
    assert "Solo tándem experimentado." in text_of(result)


def test_booking_tool_persists_and_uses_default_hour(mcp_url, monkeypatch, tmp_path):
    db = tmp_path / "bookings.sqlite3"
    monkeypatch.setenv("BOOKINGS_DB", str(db))
    monkeypatch.setattr(bookings, "fetch_weather_reading", lambda _: IDEAL)
    fecha = future_date(2)

    first = json.loads(text_of(call_tool(mcp_url, "calendarizar_cita",
                                         {"fecha_iso": fecha, "nombre_cliente": "  Ana   López "})))
    again = json.loads(text_of(call_tool(mcp_url, "calendarizar_cita",
                                         {"fecha_iso": fecha, "nombre_cliente": "ana lópez", "hora": "09:00"})))

    assert first["estado"] == "confirmada" and first["hora"] == "09:00"
    assert first["cliente"] == "Ana López" and first["ya_existia"] is False
    assert again["id"] == first["id"] and again["ya_existia"] is True
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 1


def test_faq_tool_forwards_question_and_returns_evidence(mcp_url, monkeypatch):
    seen = []
    def search(query):
        seen.append(query)
        return [{"faq_id": "FAQ-010", "answer": "La edad mínima es 18 años."}]
    monkeypatch.setattr(faqs, "search_faqs", search)

    data = json.loads(text_of(call_tool(mcp_url, "buscar_faq", {"pregunta": "¿Edad mínima?"})))

    assert seen == ["¿Edad mínima?"]
    assert data == {"resultados": [{"faq_id": "FAQ-010", "answer": "La edad mínima es 18 años."}],
                    "sin_evidencia": False}


def test_business_errors_are_returned_as_controlled_results(mcp_url, monkeypatch, tmp_path):
    db = tmp_path / "bookings.sqlite3"
    monkeypatch.setenv("BOOKINGS_DB", str(db))
    monkeypatch.setattr(bookings, "fetch_weather_reading", lambda _: LLUVIA)
    monkeypatch.setattr(faqs, "search_faqs", lambda _: (_ for _ in ()).throw(OSError("sin base")))

    weather = call_tool(mcp_url, "consultar_clima_salto", {"fecha_iso": "2026/10/10"})
    booking = json.loads(text_of(call_tool(mcp_url, "calendarizar_cita",
                                           {"fecha_iso": future_date(), "nombre_cliente": "Ana"})))
    faq = json.loads(text_of(call_tool(mcp_url, "buscar_faq", {"pregunta": "¿Horario?"})))

    assert not is_error(weather) and "Fecha inválida" in text_of(weather)
    assert booking["registrada"] is False and "No se puede reservar" in booking["error"]
    assert not db.exists() or sqlite3.connect(db).execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 0
    assert faq["resultados"] == [] and "No se pudo consultar la base de FAQs" in faq["error"]


def test_invalid_arguments_are_rejected_by_the_protocol(mcp_url):
    missing = call_tool(mcp_url, "calendarizar_cita", {"fecha_iso": future_date()})
    empty = call_tool(mcp_url, "buscar_faq", {"pregunta": ""})

    assert is_error(missing) and "nombre_cliente" in text_of(missing)
    assert is_error(empty)


def test_each_execution_is_logged_without_the_client_name(mcp_url, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="parachute.mcp")
    monkeypatch.setenv("BOOKINGS_DB", str(tmp_path / "bookings.sqlite3"))
    monkeypatch.setattr(bookings, "fetch_weather_reading", lambda _: MARGINAL)

    call_tool(mcp_url, "calendarizar_cita", {"fecha_iso": future_date(), "nombre_cliente": "Juana Pérez"})

    messages = [r.getMessage() for r in caplog.records if r.name == "parachute.mcp"]
    assert any("-> tool=calendarizar_cita" in m and "J. P." in m for m in messages)
    assert any("<- tool=calendarizar_cita OK" in m and "pendiente_revision" in m for m in messages)
    assert not any("Juana" in m for m in messages)


def test_each_agent_client_only_sees_its_own_tool(mcp_url):
    async def run():
        names = {}
        for tool_name in TOOL_NAMES:
            async with make_mcp_client("test", tool_name, url=mcp_url) as client:
                names[tool_name] = [t.name for t in await client.list_tools()]
        return names
    assert asyncio.run(run()) == {name: [name] for name in TOOL_NAMES}


def test_hierarchical_weather_agent_executes_its_tool_through_mcp(mcp_url, monkeypatch):
    monkeypatch.setattr(weather_service, "get_weather_reading", lambda _: (IDEAL, None))
    fecha = future_date()
    model = ScriptedModel([("consultar_clima_salto", {"fecha_iso": fecha}), "El salto es ideal."])

    async def run():
        async with make_mcp_client("mcp-clima", "consultar_clima_salto", url=mcp_url) as client:
            agent = weather_agent.clone(model=model, mcp_servers=[client])
            return await Runner.run(agent, f"¿Puedo saltar el {fecha}?",
                                    run_config=RunConfig(tracing_disabled=True))
    result = asyncio.run(run())

    tool_output = next(item for item in model.inputs[1] if item.get("type") == "function_call_output")
    assert "Estado del clima" in str(tool_output["output"]) and "IDEAL" in str(tool_output["output"])
    assert result.final_output == "El salto es ideal."
