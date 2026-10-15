"""Cliente SDK contra HTTP simulado y contra la aplicación A2A del grupo."""

import asyncio
import json

import httpx
import pytest

from a2a_client.main import chat
from a2a_server.server import build_agent_card, create_app
from test_a2a_server import make_executor, no_mcp


def run_chat(handler, inputs):
    outputs = []
    iterator = iter(inputs)

    def read(prompt):
        assert prompt == "Usuario: "
        value = next(iterator)
        if isinstance(value, BaseException):
            raise value
        return value

    code = asyncio.run(chat(transport=httpx.MockTransport(handler),
                            read=read, write=outputs.append))
    return code, "\n".join(outputs)


def card_response():
    return httpx.Response(200, json=build_agent_card().model_dump(mode="json", by_alias=True))


def answer(request, text="Respuesta del servidor"):
    payload = json.loads(request.content)
    return httpx.Response(200, json={
        "jsonrpc": "2.0", "id": payload["id"], "result": {
            "kind": "message", "role": "agent", "messageId": "response-id",
            "contextId": payload["params"]["message"]["contextId"],
            "parts": [{"kind": "text", "text": text}],
        },
    })


def test_discovery_send_receive_and_session():
    requests = []

    def handler(request):
        if request.method == "GET":
            assert request.url.path == "/.well-known/agent-card.json"
            return card_response()
        requests.append(json.loads(request.content))
        return answer(request)

    code, output = run_chat(handler, [" ", "Hola", "Me llamo Ana", "SALIR"])
    assert code == 0
    assert "Parachute S.A." in output
    for skill in build_agent_card().skills:
        assert skill.id in output and skill.name in output
    assert output.count("Agente: Respuesta del servidor") == 2
    assert len(requests) == 2
    assert all(request["method"] == "message/send" for request in requests)
    first, second = [request["params"]["message"] for request in requests]
    assert first["contextId"] == second["contextId"]
    assert first["messageId"] != second["messageId"]
    assert first["parts"] == [{"kind": "text", "text": "Hola"}]
    assert second["parts"][0]["text"] == "Me llamo Ana"


@pytest.mark.parametrize("failure", ["offline", "http", "invalid_card"])
def test_discovery_failure_is_readable(failure):
    def handler(request):
        if failure == "offline":
            raise httpx.ConnectError("private diagnostics", request=request)
        return httpx.Response(503 if failure == "http" else 200, json={})

    code, output = run_chat(handler, [])
    assert code == 1
    assert "No se pudo conectar" in output
    assert "Traceback" not in output and "private diagnostics" not in output


@pytest.mark.parametrize("failure", ["offline", "timeout", "rpc", "invalid_json"])
def test_failed_send_then_recovery_preserves_context(failure):
    messages = []

    def handler(request):
        if request.method == "GET":
            return card_response()
        messages.append(json.loads(request.content)["params"]["message"])
        if len(messages) == 1:
            if failure == "offline":
                raise httpx.ConnectError("private diagnostics", request=request)
            if failure == "timeout":
                raise httpx.ReadTimeout("private diagnostics", request=request)
            if failure == "invalid_json":
                return httpx.Response(200, text="not json")
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": "1",
                                            "error": {"code": -32603, "message": "private diagnostics"}})
        return answer(request, "Recuperado")

    code, output = run_chat(handler, ["Hola", "¿Sigues ahí?", "bye"])
    assert code == 0
    assert "No se pudo recibir" in output and "Agente: Recuperado" in output
    assert "private diagnostics" not in output
    assert len(messages) == 2  # No reintenta reservas automáticamente.
    assert messages[0]["contextId"] == messages[1]["contextId"]


@pytest.mark.parametrize("ending", ["bye", " SaLiR ", EOFError(), KeyboardInterrupt()])
def test_exit_without_sending(ending):
    def handler(request):
        assert request.method == "GET"
        return card_response()

    code, output = run_chat(handler, [ending])
    assert code == 0 and "Hasta luego" in output


def test_client_with_group_server_and_real_runner():
    executor, model = make_executor(["¿Tu nombre?", "Hola Ana"])
    app = create_app(executor, connector=no_mcp)
    outputs = []
    inputs = iter(["Hola", "Ana", "salir"])
    asyncio.run(chat(transport=httpx.ASGITransport(app=app),
                     read=lambda _: next(inputs), write=outputs.append))
    assert "Agente: Hola Ana" in outputs
    assert len(executor.histories) == 1
    assert "¿Tu nombre?" in str(model.inputs[1])
    assert "Ana" in str(model.inputs[1])
