"""Expone el supervisor por A2A: python -m a2a_server.server.

Autor: Juan Jose Rivas Alvarez, carnet 24856 (Persona 1).
El historial es local al proceso y se pierde al reiniciar el servidor.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message
from agents import MaxTurnsExceeded, RunHooks, Runner

from hierarchical.supervisor import supervisor
from shared.mcp_connection import connect_mcp_clients
from shared.model_config import build_run_config

HOST = "127.0.0.1"
PORT = 9999
SERVER_URL = f"http://{HOST}:{PORT}/"
logger = logging.getLogger("parachute.a2a")


def build_agent_card() -> AgentCard:
    return AgentCard(
        name="Parachute S.A. — Supervisor",
        description="Sistema multiagente de preguntas frecuentes, clima y reservas.",
        url=SERVER_URL,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        skills=[
            AgentSkill(id="preguntas_frecuentes", name="Preguntas frecuentes",
                       description="Consulta requisitos y políticas de Parachute S.A.",
                       tags=["faq"], examples=["¿Cuál es la edad mínima para salto en tándem?"]),
            AgentSkill(id="condiciones_climaticas", name="Condiciones climáticas",
                       description="Evalúa el clima para saltar en una fecha.",
                       tags=["clima"], examples=["¿Puedo saltar mañana?"]),
            AgentSkill(id="calendarizar_cita", name="Calendarizar cita",
                       description="Gestiona citas considerando las condiciones climáticas.",
                       tags=["reservas"], examples=["Quiero reservar un salto."]),
        ],
    )


class DelegationHooks(RunHooks):
    async def on_tool_start(self, context, agent, tool):
        if tool.name in {"responder_faq", "gestionar_operaciones"}:
            logger.info("delegacion=%s agente=%s", tool.name, agent.name)


class ParachuteExecutor(AgentExecutor):
    def __init__(self, agent=supervisor, config_factory=build_run_config):
        self.agent = agent
        self.config_factory = config_factory
        self.histories: dict[str, list] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        started = time.monotonic()
        context_id = context.context_id
        logger.info("request recibida context_id=%s", context_id)
        message = context.message
        # El contrato acepta mensajes de texto; no omitir silenciosamente archivos.
        if (message is None or not message.parts
                or any(part.root.kind != "text" for part in message.parts)
                or not context.get_user_input().strip()):
            response = "Envía un mensaje de texto no vacío."
        else:
            lock = self.locks.setdefault(context_id, asyncio.Lock())
            async with lock:
                history = self.histories.get(context_id, [])
                inputs = [*history, {"role": "user", "content": context.get_user_input()}]
                try:
                    result = await Runner.run(
                        self.agent, inputs, run_config=self.config_factory(),
                        hooks=DelegationHooks(),
                    )
                    response = str(result.final_output)
                    # Un turno fallido nunca deja un historial parcial.
                    self.histories[context_id] = result.to_input_list()
                except MaxTurnsExceeded:
                    logger.warning("error=max_turns context_id=%s", context_id)
                    response = "La solicitud excedió el límite de pasos. Intenta una consulta más específica."
                except Exception as exc:
                    # No publicar claves, prompts o detalles privados de proveedores.
                    logger.error("error=%s context_id=%s", type(exc).__name__, context_id)
                    response = "No se pudo completar la solicitud. Verifica los servicios y vuelve a intentarlo."
        await event_queue.enqueue_event(new_agent_text_message(response, context_id=context_id))
        logger.info("respuesta context_id=%s duracion=%.3fs caracteres=%d",
                    context_id, time.monotonic() - started, len(response))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        from a2a.types import UnsupportedOperationError
        from a2a.utils.errors import ServerError

        raise ServerError(error=UnsupportedOperationError())


def create_app(executor: ParachuteExecutor | None = None, *, connector=connect_mcp_clients):
    @asynccontextmanager
    async def lifespan(app):
        # Mantiene las tres conexiones abiertas durante toda la vida del servidor.
        async with connector():
            logger.info("Clientes MCP conectados; servidor A2A disponible en %s", SERVER_URL)
            yield

    handler = DefaultRequestHandler(
        agent_executor=executor or ParachuteExecutor(), task_store=InMemoryTaskStore(),
    )
    return A2AStarletteApplication(
        agent_card=build_agent_card(), http_handler=handler,
    ).build(lifespan=lifespan)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
