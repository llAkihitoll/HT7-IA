# HT7 — Protocolos agénticos para Parachute S.A.

El sistema multiagente jerárquico se expone como un solo agente mediante
**A2A JSON-RPC 0.3**. La terminal descubre su Agent Card y conversa por HTTP.
Los especialistas ejecutan sus herramientas en un único servidor **MCP con
Streamable HTTP**. El cliente de terminal no importa ni ejecuta los agentes.

## Arquitectura

```mermaid
flowchart TD
    Terminal[Usuario en terminal] --> Client[Cliente A2A: a2a_client.main]
    Client -->|Agent Card + message/send HTTP :9999| Server[Servidor A2A]
    Server -->|Runner + historial por context_id| Supervisor[Supervisor]
    Supervisor -->|responder_faq| FAQ[Agente FAQs]
    Supervisor -->|gestionar_operaciones| Manager[Submanager de operaciones]
    Manager --> Weather[Agente Clima]
    Manager --> Booking[Agente Reservas]
    FAQ -->|Cliente MCP| MCP[Servidor MCP: Streamable HTTP :8001/mcp]
    Weather -->|Cliente MCP| MCP
    Booking -->|Cliente MCP| MCP
    MCP --> Search[buscar_faq]
    MCP --> Forecast[consultar_clima_salto]
    MCP --> Reserve[calendarizar_cita]
    Search --> PG[(PostgreSQL + pgvector: 120 FAQs)]
    Forecast --> OpenMeteo[Open-Meteo + evaluación climática]
    Reserve --> OpenMeteo
    Reserve --> SQLite[(SQLite: reservas)]
```

| Componente | Responsabilidad |
|---|---|
| `a2a_client/main.py` | Descubre el agente, muestra nombre/skills, envía texto y presenta respuestas/errores |
| `a2a_server/server.py` | Agent Card, ejecución del supervisor, historial en memoria y logs A2A |
| `hierarchical/` | Supervisor → FAQ / submanager → clima / reservas |
| `shared/mcp_connection.py` | Tres clientes MCP, cada uno filtrado a la herramienta de su especialista |
| `mcp_server/server.py` | Un solo servidor con las tres herramientas y logs de sus ejecuciones |
| `shared/` | Búsqueda semántica, clima y persistencia de reservas reutilizados de laboratorios anteriores |

## Preparación

Usar Python **3.12 o 3.13**, Docker Desktop iniciado y una clave de NVIDIA NIM
u OpenAI para la demostración real. Ejecutar desde la raíz de este repositorio.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

En Windows PowerShell: `py -3.13 -m venv .venv`, `.venv\Scripts\Activate.ps1`
y `Copy-Item .env.example .env`. No sobrescribir un `.env` ya configurado.

Configurar `NVIDIA_API_KEY` en `.env` (por defecto usa `openai/gpt-oss-20b`);
si está vacía, configurar `OPENAI_API_KEY`. `AGENT_MODEL` permite elegir el
modelo de NVIDIA. No subir `.env` ni mostrar las claves en el video.
La terminal A2A no necesita claves: las usa el proceso servidor.

```bash
docker compose up -d --wait
python -m shared.faq_store.load_data
python -m pytest -q
```

La carga es idempotente y debe terminar con **120 FAQs**, embeddings locales
`all-MiniLM-L6-v2` de 384 dimensiones. La primera ejecución descarga el modelo.
HT7 usa el proyecto Compose `ht7-ia`, un volumen propio y puerto **5434** para
no reutilizar accidentalmente la base de HT5. La configuración incluida es:

```dotenv
POSTGRES_PORT=5434
DATABASE_URL=postgresql://parachute:parachute_local@localhost:5434/parachute_faqs?connect_timeout=5
MCP_SERVER_URL=http://127.0.0.1:8001/mcp
BOOKINGS_DB=data/bookings.sqlite3
```

## Ejecución completa: tres terminales

Activar `.venv` y ubicarse en este repositorio en **cada terminal**.
Arrancar en este orden y esperar a que cada servicio esté disponible:

```bash
# Terminal 1: herramientas y logs MCP
python -m mcp_server.server
```

```bash
# Terminal 2: sistema multiagente y logs A2A
python -m a2a_server.server
```

```bash
# Terminal 3: interacción con el agente remoto
python -m a2a_client.main
```

La terminal muestra el nombre del agente y las skills `preguntas_frecuentes`,
`condiciones_climaticas` y `calendarizar_cita`. Luego presenta `Usuario:`.
`salir`, `bye` (sin distinguir mayúsculas), Ctrl+C y EOF cierran la sesión;
las líneas vacías no se envían. Para otro servidor:
`python -m a2a_client.main --url http://127.0.0.1:9999`.

### Contrato A2A

- Agent Card: `http://127.0.0.1:9999/.well-known/agent-card.json`.
- Transporte JSON-RPC, método `message/send`; entrada/salida de texto sin streaming.
- Un `context_id` por sesión de terminal y un `message_id` nuevo por mensaje.
  El servidor conserva el historial por contexto en memoria; reiniciarlo lo pierde.
- El cliente usa `A2ACardResolver` y `ClientFactory` de `a2a-sdk`.
- Una falla de conexión inicial termina con mensaje claro y código 1.
  Una falla durante la conversación permite seguir escribiendo con el mismo contexto.
  No se reenvían mensajes automáticamente: una reserva podría haberse procesado.
- Conexión: máximo 5 segundos; espera de respuesta: hasta 300 segundos, pues una
  consulta puede ejecutar varios agentes y herramientas.
- El servidor captura errores del modelo y límite de turnos, y devuelve texto
  comprensible sin detenerse. Los logs incluyen contexto, delegación y duración.

### Contrato MCP

| Herramienta | Implementación | Consumidor |
|---|---|---|
| `buscar_faq(pregunta)` | Búsqueda semántica en PostgreSQL/pgvector | Agente FAQs |
| `consultar_clima_salto(fecha_iso)` | Open-Meteo + evaluador | Agente Clima |
| `calendarizar_cita(fecha_iso, nombre_cliente, hora="09:00")` | Verificación climática + SQLite | Agente Reservas |

El servidor usa Streamable HTTP en `http://127.0.0.1:8001/mcp`.
Los logs muestran `-> tool=...`, `<- tool=... OK` o errores.
`MCP_WARMUP=0` omite la precarga de embeddings, pero las consultas FAQ reales
siguen necesitando el modelo y PostgreSQL.

## Casos para la demostración y el video

Ver el [guion de grabación](docs/VIDEO_HT7.md) para mostrar las tres terminales.

1. FAQ: «¿Cuál es la edad mínima para salto en tándem?».
2. Clima: consultar una fecha entre hoy y hoy + 15 días en Guatemala.
3. Reserva: proporcionar fecha, hora y nombre; confirmar lo que solicite el agente.
4. Error de datos: consultar `2026-02-30`.
5. Error de conexión: detener A2A con Ctrl+C en terminal 2 y enviar otro mensaje
   desde terminal 3; debe aparecer un mensaje claro, sin traceback.

El veredicto meteorológico depende del pronóstico del día de la prueba.
**No se debe forzar ni prometer un resultado PROHIBIDO**. Ideal confirma;
marginal queda pendiente de revisión; prohibido/error no guarda la reserva.
El servidor reconsulta el clima al reservar. La fecha, hora y nombre deben
acordarse con el usuario; no se implementan pagos ni cupos ni Google Calendar.

## Pruebas

```bash
python -m pytest -q
python -m pytest -q tests/test_a2a_client.py tests/test_a2a_server.py
```

Las pruebas no necesitan claves ni servicios externos. Cubren descubrimiento,
envío/recepción, continuidad de contexto, salida, errores de red/protocolo y
recuperación. El cliente se prueba además contra la aplicación A2A real y el
Runner del SDK con modelo simulado; la suite del servidor integra también el
transporte MCP real. Estas pruebas no sustituyen la demostración con LLM,
PostgreSQL, Open-Meteo y grabación reales.

Validación local de esta implementación (14 de octubre de 2026, Guatemala):
**113 pruebas y 5 subpruebas pasaron** en Python 3.12. La carga real en
PostgreSQL verificó **120 filas, 6 categorías, 384 dimensiones e IDs únicos**.
La conversación con LLM y el video quedan pendientes de configurar una clave.

## Solución de problemas

- **No conecta A2A:** iniciar primero MCP y después A2A; revisar puertos 8001/9999.
- **A2A no arranca:** comprobar `MCP_SERVER_URL` y los logs de terminal 1.
- **FAQ falla:** iniciar Docker, cargar las 120 FAQs y revisar `DATABASE_URL`.
- **Falla el modelo:** comprobar la clave y disponibilidad del proveedor en terminal 2.
- **Timeout en cliente:** revisar los logs antes de repetir una reserva.
- **Certificados en macOS:** configurar el almacén TLS; si el entorno lo necesita,
  `export SSL_CERT_FILE="$(python -m certifi)"`. No deshabilitar HTTPS.

Detener cliente, A2A y MCP con Ctrl+C. `docker compose down` detiene PostgreSQL
sin borrar el volumen. Las reservas permanecen en SQLite local.

## Código y documentación heredados

`centralized.main`, `hierarchical.main` y `decentralized.main` conservan las demos
anteriores; **la terminal de esta entrega es `a2a_client.main`**. Los documentos
siguientes describen el proyecto previo y no sustituyen las instrucciones HT7:

- [Arquitectura jerárquica](diagrams/hierarchical_architecture.md)
- [Arquitectura centralizada](diagrams/centralized_architecture.md)
- [Arquitectura descentralizada](diagrams/decentralized_architecture.md)
- [Respuestas de HT5](docs/RESPUESTAS.md)
