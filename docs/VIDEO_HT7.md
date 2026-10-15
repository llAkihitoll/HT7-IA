# Guion del video — HT7

Este archivo es una guía de grabación, no evidencia de una grabación realizada.
La entrega requiere subir el video además del repositorio.

## Antes de grabar

1. Seguir la preparación del README: clave del modelo, Docker y 120 FAQs cargadas.
2. Abrir tres terminales visibles simultáneamente, con letra legible y títulos
   «MCP», «A2A» y «Cliente». Activar `.venv` en cada una.
3. Elegir una fecha válida de hoy a hoy + 15 días, según Guatemala. Puede obtenerse con:

   ```bash
   python -c "from datetime import datetime,timedelta; from zoneinfo import ZoneInfo; print((datetime.now(ZoneInfo('America/Guatemala')).date()+timedelta(days=3)).isoformat())"
   ```

4. Usar un nombre ficticio para la reserva de demostración. No mostrar `.env`.
5. Iniciar la grabación de pantalla; en macOS, Cmd+Shift+5 permite grabar un área
   con las tres terminales. Activar micrófono si desean narrar.

## Secuencia sugerida (4–6 minutos)

| Momento | Acción visible | Explicación |
|---|---|---|
| Inicio | Mostrar el Mermaid del README brevemente | La terminal usa A2A para hablar con un MAS; sus tools están centralizadas en MCP |
| Servicios | Ejecutar `python -m mcp_server.server` y luego `python -m a2a_server.server` | MCP usa Streamable HTTP; A2A envuelve el supervisor |
| Descubrimiento | Ejecutar `python -m a2a_client.main` | Se obtiene Agent Card y se muestran nombre y las tres skills |
| FAQ | «¿Cuál es la edad mínima para salto en tándem?» | Señalar delegación A2A, logs MCP `buscar_faq` y respuesta con evidencia |
| Clima | «¿Puedo saltar el FECHA_ELEGIDA?» | Señalar `consultar_clima_salto` y explicar el veredicto real |
| Reserva | «Reserva para esa fecha a las 09:00, mi nombre es Ana Demo» | Mostrar contexto compartido, confirmar si lo pide y observar `calendarizar_cita` |
| Validación | «¿Puedo saltar el 2026-02-30?» | Mostrar rechazo entendible de la fecha inválida |
| Servidor caído | Ctrl+C en A2A; luego escribir «Hola» en el cliente | Mensaje de conexión claro, sin traceback en cliente |
| Cierre | Escribir `bye` | La sesión termina limpiamente |

Si el clima impide reservar, el rechazo es correcto. Si es marginal o ideal,
explicar el estado devuelto. No presentar respuestas simuladas como ejecución real.
Los logs A2A deben mostrar request, delegación y duración; los de MCP, entrada y
resultado de cada tool. Una fecha inválida puede ser rechazada por el agente antes
de invocar una herramienta; las consultas válidas anteriores muestran el transporte.

## Antes de entregar

- Revisar que se vean las tres terminales y las herramientas ejecutadas.
- Revisar audio, texto legible y ausencia de claves.
- Guardar/exportar la grabación y subirla por el medio solicitado por el curso.
- Entregar el enlace del repositorio con los cambios de Persona 2 incluidos.
