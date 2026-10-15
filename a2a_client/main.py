"""Terminal A2A: python -m a2a_client.main (sin acceso directo al MAS)."""

from __future__ import annotations

import argparse
import asyncio
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.client.errors import A2AClientError
from a2a.types import Message, Part, Role, TextPart, TransportProtocol

DEFAULT_URL = "http://127.0.0.1:9999"


async def chat(base_url=DEFAULT_URL, *, transport=None, read=input, write=print) -> int:
    """Una sesión por ejecución; transport/read/write permiten pruebas sin LLM."""
    timeout = httpx.Timeout(300.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as http:
        try:
            card = await A2ACardResolver(http, base_url).get_agent_card()
            client = ClientFactory(ClientConfig(
                httpx_client=http, streaming=False,
                supported_transports=[TransportProtocol.jsonrpc],
            )).create(card)
        except (A2AClientError, httpx.HTTPError, ValueError):
            write(f"No se pudo conectar al servidor A2A en {base_url}. "
                  "Inicia MCP y luego ejecuta python -m a2a_server.server.")
            return 1

        write(f"Conectado a: {card.name}")
        for skill in card.skills:
            write(f"  - {skill.name} ({skill.id}): {skill.description}")
        write("Escribe salir o bye para terminar; también puedes usar Ctrl+C.")
        context_id = uuid4().hex
        while True:
            try:
                text = read("Usuario: ").strip()
            except (EOFError, KeyboardInterrupt):
                write("\nHasta luego.")
                return 0
            if text.casefold() in {"salir", "bye"}:
                write("Hasta luego.")
                return 0
            if not text:
                continue
            message = Message(
                role=Role.user, message_id=uuid4().hex, context_id=context_id,
                parts=[Part(root=TextPart(text=text))],
            )
            try:
                received_text = False
                async for event in client.send_message(message):
                    # El servidor de HT7 devuelve Message; también se admite Task.
                    if isinstance(event, Message):
                        parts = event.parts
                    else:
                        task, _ = event
                        parts = [part for artifact in (task.artifacts or [])
                                 for part in artifact.parts]
                        if not parts and task.status.message:
                            parts = task.status.message.parts
                    response = "\n".join(part.root.text for part in parts
                                         if isinstance(part.root, TextPart))
                    if response:
                        write(f"Agente: {response}")
                        received_text = True
                if not received_text:
                    write("El servidor no devolvió una respuesta de texto.")
            except (A2AClientError, httpx.HTTPError, ValueError):
                write("No se pudo recibir la respuesta A2A. Verifica que el servidor "
                      "siga activo. La solicitud pudo haberse procesado; consulta "
                      "su estado antes de repetir una reserva.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cliente de terminal A2A de Parachute S.A.")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL base del servidor A2A")
    args = parser.parse_args()
    try:
        return asyncio.run(chat(args.url))
    except KeyboardInterrupt:
        print("\nHasta luego.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
