"""Contrato HTTP A2A y Runner real, sin claves ni llamadas a un LLM remoto."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from agents import Agent, RunConfig, function_tool
from starlette.testclient import TestClient

from a2a_server.server import ParachuteExecutor, create_app
from test_decentralized import ScriptedModel
from test_mcp_server import mcp_url  # noqa: F401 — fixture HTTP real


@asynccontextmanager
async def no_mcp():
    yield


def send(client, text="Hola", context_id=None, parts=None):
    message = {"role": "user", "messageId": uuid4().hex,
               "parts": parts if parts is not None else [{"kind": "text", "text": text}]}
    if context_id:
        message["contextId"] = context_id
    response = client.post("/", json={"jsonrpc": "2.0", "id": uuid4().hex,
                                     "method": "message/send", "params": {"message": message}})
    assert response.status_code == 200
    return response.json()


def reply(data):
    return data["result"]["parts"][0]["text"]


def make_executor(steps, agent=None):
    model = ScriptedModel(steps)
    executor = ParachuteExecutor(
        agent=agent or Agent(name="Prueba"),
        config_factory=lambda: RunConfig(model=model, tracing_disabled=True),
    )
    return executor, model


def test_card_and_mcp_lifecycle():
    events = []

    @asynccontextmanager
    async def connector():
        events.append("connected")
        try:
            yield
        finally:
            events.append("closed")

    with TestClient(create_app(connector=connector)) as client:
        assert events == ["connected"]
        response = client.get("/.well-known/agent-card.json")
        assert response.status_code == 200
        card = response.json()
        assert card["url"] == "http://127.0.0.1:9999/"
        assert {skill["id"] for skill in card["skills"]} == {
            "preguntas_frecuentes", "condiciones_climaticas", "calendarizar_cita"}
        assert card["defaultInputModes"] == card["defaultOutputModes"] == ["text/plain"]
        assert card["capabilities"]["streaming"] is False
    assert events == ["connected", "closed"]


def test_context_is_reused_and_other_sessions_are_isolated():
    executor, model = make_executor(["¿Tu nombre?", "Hola Juan", "Otra sesión"])
    with TestClient(create_app(executor, connector=no_mcp)) as client:
        first = send(client)
        context_id = first["result"]["contextId"]
        assert reply(first) == "¿Tu nombre?"
        second = send(client, "Juan", context_id)
        assert reply(second) == "Hola Juan"
        assert second["result"]["contextId"] == context_id
        third = send(client, "Nueva consulta")
        assert third["result"]["contextId"] != context_id
    assert "¿Tu nombre?" in str(model.inputs[1])
    assert "Juan" in str(model.inputs[1])
    assert "Juan" not in str(model.inputs[2])


def test_simultaneous_messages_in_same_context_do_not_lose_history():
    executor, model = make_executor(["Primera respuesta", "Segunda respuesta"])
    original = model.get_response

    async def slow_response(*args, **kwargs):
        await asyncio.sleep(0.03)
        return await original(*args, **kwargs)

    model.get_response = slow_response
    with TestClient(create_app(executor, connector=no_mcp)) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda text: send(client, text, "shared-session"), ["Uno", "Dos"]))
    assert {reply(data) for data in results} == {"Primera respuesta", "Segunda respuesta"}
    history = executor.histories["shared-session"]
    assert len([item for item in history if item.get("role") == "user"]) == 2
    assert "Primera respuesta" in str(model.inputs[1])


@pytest.mark.parametrize("tool_name", ["responder_faq", "gestionar_operaciones"])
def test_real_runner_delegates_and_logs(tool_name, caplog):
    specialist = Agent(name="Especialista")
    agent = Agent(name="Supervisor", tools=[specialist.as_tool(
        tool_name=tool_name, tool_description="Delega la consulta")])
    executor, model = make_executor([
        (tool_name, {"input": "Consulta"}), "Respuesta especialista", "Respuesta final",
    ], agent)
    caplog.set_level(logging.INFO, logger="parachute.a2a")
    with TestClient(create_app(executor, connector=no_mcp)) as client:
        assert reply(send(client)) == "Respuesta final"
    assert "Respuesta especialista" in str(model.inputs[-1])
    assert f"delegacion={tool_name}" in caplog.text
    assert "request recibida" in caplog.text and "duracion=" in caplog.text


@pytest.mark.parametrize("failure", ["provider", "max_turns", "config"])
def test_errors_leave_history_intact_and_server_recovers(failure):
    agent = Agent(name="Prueba")
    if failure == "max_turns":
        @function_tool
        def repetir() -> str:
            return "Repetir"
        agent = agent.clone(tools=[repetir])
        steps = [("repetir", {})] * 10 + ["Recuperado"]
    else:
        steps = ["Recuperado"]
    executor, model = make_executor(steps, agent)
    good_factory = executor.config_factory
    if failure == "provider":
        original = model.get_response

        async def fail(*args, **kwargs):
            raise RuntimeError("private-key-provider-details")

        model.get_response = fail
    elif failure == "config":
        def fail_config():
            raise RuntimeError("private-key-config-details")
        executor.config_factory = fail_config
    with TestClient(create_app(executor, connector=no_mcp)) as client:
        data = send(client, context_id="session-error")
        expected = "límite" if failure == "max_turns" else "No se pudo"
        assert expected in reply(data)
        assert "private-key" not in reply(data)
        assert executor.histories == {}
        if failure == "provider":
            model.get_response = original
        executor.config_factory = good_factory
        model.steps = iter(["Recuperado"])
        assert reply(send(client, context_id="session-error")) == "Recuperado"


@pytest.mark.parametrize("parts", [[{"kind": "text", "text": "  "}],
                                  [{"kind": "data", "data": {"x": 1}}]])
def test_non_text_or_empty_input_is_controlled(parts):
    executor, model = make_executor([])
    with TestClient(create_app(executor, connector=no_mcp)) as client:
        assert "texto no vacío" in reply(send(client, parts=parts))
    assert model.inputs == [] and executor.histories == {}


def test_malformed_rpc_does_not_stop_server():
    executor, _ = make_executor(["Sigo disponible"])
    with TestClient(create_app(executor, connector=no_mcp)) as client:
        bad = client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "inexistente"})
        assert "error" in bad.json()
        assert reply(send(client)) == "Sigo disponible"


def test_cancellation_is_explicitly_unsupported():
    from a2a.utils.errors import ServerError

    executor, _ = make_executor([])
    with pytest.raises(ServerError):
        asyncio.run(executor.cancel(None, None))


def test_a2a_supervisor_faq_and_real_mcp_transport(mcp_url, monkeypatch):
    from hierarchical.faq_agent_stub import faq_agent
    from hierarchical.supervisor import supervisor
    from shared import faqs
    from shared.mcp_connection import make_mcp_client

    seen = []

    def search(question):
        seen.append(question)
        return [{"faq_id": "FAQ-010", "answer": "La edad mínima es 18 años."}]

    monkeypatch.setattr(faqs, "search_faqs", search)
    mcp_client = make_mcp_client("a2a-test-faq", "buscar_faq", url=mcp_url)
    specialist = faq_agent.clone(mcp_servers=[mcp_client])
    agent = supervisor.clone(tools=[specialist.as_tool(
        tool_name="responder_faq", tool_description="Responde FAQs")])
    executor, model = make_executor([
        ("responder_faq", {"input": "¿Edad mínima?"}),
        ("buscar_faq", {"pregunta": "¿Edad mínima?"}),
        "La edad mínima es 18 años [FAQ-010].",
        "La edad mínima es 18 años [FAQ-010].",
    ], agent)

    @asynccontextmanager
    async def connector():
        async with mcp_client:
            yield

    with TestClient(create_app(executor, connector=connector)) as client:
        assert "18 años [FAQ-010]" in reply(send(client, "¿Edad mínima?"))
    assert seen == ["¿Edad mínima?"]
    assert "FAQ-010" in str(model.inputs[-1])
