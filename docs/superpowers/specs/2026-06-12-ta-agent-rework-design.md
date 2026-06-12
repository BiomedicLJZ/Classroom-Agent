# TA Agent Rework — Razonamiento Nemotron 3, Streaming, Reescritura Universal y Admin Ampliado

**Fecha:** 2026-06-12
**Estado:** Aprobado por el instructor (Leonardo)

## Contexto

El agente TA (LangGraph + deepagents + ChatNVIDIA) opera Google Classroom con dos
cuentas (cugdl/uniat). Estado actual:

- `ta/agent.py` crea `ChatNVIDIA(model, api_key)` sin parámetros de muestreo ni
  razonamiento. Los prompts usan el prefijo legacy `"detailed thinking on/off"`
  (toggle de Nemotron-1 que Nemotron 3 no usa).
- `ta/cli.py` streamea con `stream_mode="updates"`: imprime mensajes completos al
  terminar cada nodo. No hay tokens en vivo ni razonamiento visible.
- La reescritura de entradas existe solo como guideline #1 del system prompt y
  solo cubre assignments.
- Faltan operaciones admin: editar/borrar posts, topics, exportar calificaciones.

## Objetivos

1. Activar el razonamiento nativo de `nvidia/nemotron-3-ultra-550b-a55b` con los
   parámetros del endpoint gratuito de NVIDIA.
2. Streaming token a token en la CLI, mostrando el razonamiento crudo (gris dim)
   antes de la respuesta.
3. Todo texto del instructor destinado a estudiantes se mejora/reescribe antes de
   entregarse vía API, con gate de confirmación (mostrar → y/N → publicar).
4. Nuevas herramientas admin: editar/borrar assignments, anuncios y materiales;
   topics; exportar calificaciones a Excel.

## No-objetivos

- Comentarios públicos en posts de Classroom (la API v1 no los expone — ver
  Limitaciones).
- Rewrite async de la CLI (`astream_events`).
- Cambios al flujo multi-cuenta o a la autenticación más allá de scopes nuevos.

---

## 1. Modelo con razonamiento — `ta/config.py` + `ta/agent.py`

`Settings` gana cinco campos, overridables por `.env`:

| Campo | Default |
|---|---|
| `nvidia_temperature` | `1.0` |
| `nvidia_top_p` | `0.95` |
| `nvidia_max_tokens` | `16384` |
| `nvidia_reasoning_budget` | `16384` |
| `nvidia_enable_thinking` | `True` |

`build_agent` construye:

```python
llm = ChatNVIDIA(
    model=settings.nvidia_model,
    api_key=settings.nvidia_api_key,
    temperature=settings.nvidia_temperature,
    top_p=settings.nvidia_top_p,
    max_tokens=settings.nvidia_max_tokens,
    reasoning_budget=settings.nvidia_reasoning_budget,
    chat_template_kwargs={"enable_thinking": settings.nvidia_enable_thinking},
)
```

- Se eliminan los prefijos `"detailed thinking on"` (SYSTEM_PROMPT) y
  `"detailed thinking off"` (_GRADING_SUBAGENT_PROMPT).
- El mismo `llm` alimenta agente principal y subagente de grading: ambos razonan
  (decisión del instructor — endpoint gratuito, costo monetario cero).
- Requiere `langchain-nvidia-ai-endpoints>=1.4.0` (ya en pyproject), que acepta
  `reasoning_budget` y `chat_template_kwargs` como kwargs del constructor.

## 2. Streaming CLI — `ta/cli.py`

**Decisión:** `graph.stream(..., stream_mode=["messages", "updates"])` (opción A).
Con lista de modos, cada item del stream es una tupla `(modo, payload)`.

- **`"messages"`** → `(AIMessageChunk, metadata)` por token de toda llamada LLM:
  - Razonamiento: `chunk.additional_kwargs.get("reasoning_content")` — se imprime
    en gris dim, token a token, bajo header `🧠 thinking`.
  - Respuesta: `chunk.content` — texto normal, streameado después del thinking.
  - Parser defensivo: si `reasoning_content` no está, buscar bloques tipo
    `"reasoning"` en `content_blocks`/listas de content (la forma exacta varía por
    versión de langchain-nvidia-ai-endpoints; se verifica con llamada real).
  - Tokens del subagente de grading: mismo stream con tag `[grading]`
    (distinguido vía `metadata["langgraph_node"]` / tags del runnable).
- **`"updates"`** → dos usos:
  - `__interrupt__`: el flujo de confirmación y/N actual se conserva íntegro
    (incluye lote múltiple y one-by-one).
  - Mensajes de tool: imprimir aviso de una línea `⚙ <tool_name>...` al ejecutarse
    cada herramienta. Los mensajes AI que lleguen por "updates" NO se imprimen
    (ya salieron token a token por "messages") — evita doble impresión.
- El `Panel` de Rich para respuestas AI desaparece (no se puede streamear dentro de
  un panel); lo reemplazan headers simples. El panel de bienvenida se queda.

## 3. Reescritura universal — system prompt

Nueva sección `REWRITE PROTOCOL` en `SYSTEM_PROMPT` de `ta/agent.py`:

- Aplica a TODO texto destinado a estudiantes: anuncios, títulos y descripciones
  de assignments, descripciones de materiales, feedback de calificación,
  comentarios privados.
- Reglas: corregir ortografía/gramática; tono profesional cálido; estructura clara
  (para assignments: objetivos de aprendizaje, instrucciones paso a paso, criterios
  de entrega); preservar el idioma del input (es/en); expandir notas sueltas a
  contenido completo y pulido.
- Flujo: el agente redacta la versión mejorada → el gate `interrupt()` existente la
  muestra → instructor confirma y/N → se publica. Una sola pausa.
- Ajuste a tools para visibilidad total: los `details` del interrupt incluyen el
  texto completo que se publicará (hoy `post_announcement` trunca a 200 chars;
  `create_assignment` omite la descripción). Aplica a `post_announcement`,
  `create_assignment`, `create_material` y los nuevos `update_*`.
- El prompt documenta la limitación de comentarios públicos y la alternativa
  (`post_private_comment` por alumno o anuncio referenciando el assignment).

## 4. Herramientas nuevas — `ta/tools/classroom.py` + `ta/tools/grading.py`

Siguen el patrón existente: `@tool`, `_classroom_service(get_active_account())`,
`_http_error_msg`, `interrupt()` en writes.

| Tool | Endpoint | Confirmación |
|---|---|---|
| `update_assignment(course_id, coursework_id, title?, description?, due_date?, due_time?, max_points?, state?, topic_id?)` | `courseWork.patch` + `updateMask` solo con campos provistos | sí |
| `delete_assignment(course_id, coursework_id)` | `courseWork.delete` | sí |
| `list_announcements(course_id)` | `announcements.list` | no |
| `update_announcement(course_id, announcement_id, text?, state?)` | `announcements.patch` | sí |
| `delete_announcement(course_id, announcement_id)` | `announcements.delete` | sí |
| `list_materials(course_id)` | `courseWorkMaterials.list` | no |
| `update_material(course_id, material_id, title?, description?)` | `courseWorkMaterials.patch` | sí |
| `delete_material(course_id, material_id)` | `courseWorkMaterials.delete` | sí |
| `list_topics(course_id)` | `topics.list` | no |
| `create_topic(course_id, name)` | `topics.create` | no (bajo riesgo) |
| `export_grades(course_id, output_path)` | submissions + roster + coursework → xlsx | no |

- `due_date`/`due_time` opcionales, formatos `YYYY-MM-DD` / `HH:MM` (igual que
  `create_assignment`).
- Asignar coursework a topic = `update_assignment(topic_id=...)`.
- `export_grades`: matriz alumnos × assignments en una hoja "Grades" —
  columnas: nombre, email, una columna por coursework (título), celda =
  `assignedGrade` (vacía si no calificado). Escribe `.xlsx` vía openpyxl
  (dependencia existente). Va en `grading.py`.
- Todas se registran en `ALL_TOOLS` (`ta/tools/__init__.py`).

### Scopes — `ta/google_auth.py`

Se agregan a `SCOPES`:

- `https://www.googleapis.com/auth/classroom.topics`
- `https://www.googleapis.com/auth/classroom.courseworkmaterials`

**Consecuencia:** tokens existentes quedan inválidos para los scopes nuevos. El
instructor debe borrar `credentials/token.json` (y el de uniat cuando exista) y
re-correr el flujo OAuth una vez por cuenta.

## 5. Tests — `tests/`

- `test_agent.py`: `ChatNVIDIA` recibe temperature/top_p/max_tokens/
  reasoning_budget/chat_template_kwargs desde Settings; prompts ya no contienen
  "detailed thinking".
- `test_cli.py`: stream fake de tuplas `(modo, payload)` — chunks con
  `reasoning_content`, chunks de content, `__interrupt__` simple y múltiple;
  verifica orden de display (thinking antes que respuesta), tag `[grading]`,
  no-doble-impresión, y resume con `Command`.
- `test_classroom_admin.py` (o dentro del existente): mocks del service para
  patch/delete/topics; rutas confirmado/cancelado del interrupt; `updateMask`
  correcto con campos parciales.
- `test_grading.py`: `export_grades` produce xlsx con matriz esperada (mock de
  API, archivo real en tmp_path).
- `ruff check` limpio.

## Riesgos

1. **Forma del chunk de razonamiento** varía por versión de
   `langchain-nvidia-ai-endpoints` (`additional_kwargs["reasoning_content"]` vs
   content blocks). Mitigación: parser defensivo + verificación con llamada real
   al endpoint durante implementación.
2. **Re-auth obligatorio** por scopes nuevos — operaciones fallan con 403 hasta
   re-autenticar. Mitigación: documentar en README/mensaje de arranque.
3. **Endpoint gratuito**: rate limits con grading masivo + thinking. Aceptado por
   el instructor.

## Limitaciones documentadas

- La API v1 de Classroom no expone comentarios públicos en stream items
  (assignments/anuncios). "Comentar un assignment" se resuelve con
  `post_private_comment` por alumno o un anuncio que lo referencie.
