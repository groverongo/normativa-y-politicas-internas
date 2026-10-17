# Asistente normativo SBS: endpoints, proceso, casos y agentes

Guía funcional del backend: qué hace cada endpoint, cómo avanza una consulta por el pipeline de agentes,
tres casos de uso completos y cómo reemplazar los agentes de ejemplo por agentes reales con un LLM.

- API desplegada: `http://ec2-54-86-250-167.compute-1.amazonaws.com` (Swagger en `/docs`)
- En los ejemplos, `API` es esa URL o `http://127.0.0.1:8000` si corres en local.

## Índice

1. [Cómo funciona, en una imagen](#1-cómo-funciona-en-una-imagen)
2. [Endpoints](#2-endpoints)
3. [El proceso de una consulta, paso a paso](#3-el-proceso-de-una-consulta-paso-a-paso)
4. [Casos de uso](#4-casos-de-uso)
5. [Implementar los agentes reales](#5-implementar-los-agentes-reales)
6. [Agregar o cambiar agentes del pipeline](#6-agregar-o-cambiar-agentes-del-pipeline)

---

## 1. Cómo funciona, en una imagen

```
 UI / analista            API (FastAPI)                     PostgreSQL (RDS)          Orquestador (2º plano)
 ─────────────            ─────────────                     ────────────────          ──────────────────────
 POST /consultas ───────► crea ejecucion (PENDIENTE) ─────► ejecucion
 ◄── 202 {ejecucion_id}   y lanza el pipeline ─────────────────────────────────────►  por cada agente:
                                                                                       1. paso_actual = AGENTE,
 GET /consultas/{id} ───► lee ejecucion + pasos ◄────────── ejecucion, paso_agente ◄──    estado = EN_PROCESO
 (cada 1-2 s)             ◄── estado, paso_actual, pasos                               2. corre el agente
                                                                                       3. guarda paso_agente
 ... hasta COMPLETADO                                                                     (salida, duracion_ms)
     o ERROR                                                                           al final: respuesta,
                                                                                       estado = COMPLETADO
```

Pipeline: **BUSCADOR → VIGENCIA → CONFLICTOS → REDACTOR**. Cada agente recibe la pregunta y lo que
devolvieron los anteriores.

| Agente     | Qué hace                                                                 | Devuelve                                   |
|------------|--------------------------------------------------------------------------|--------------------------------------------|
| BUSCADOR   | Encuentra artículos relevantes en normas SBS y políticas internas        | `articulos` con documento, artículo, fragmento y score |
| VIGENCIA   | Separa lo vigente de lo derogado o reemplazado                           | `vigentes` y `descartados` (con motivo y reemplazo) |
| CONFLICTOS | Detecta contradicciones entre los artículos vigentes                     | `conflictos` entre pares de documentos     |
| REDACTOR   | Redacta la respuesta final para el analista                              | `respuesta`, `citas` y `alertas`           |

**Trazabilidad completa**, todo consultable después:

```
ejecucion (pregunta) → paso_agente (agente, salida) → artículo (salida.articulos[].documento_id)
   → documento (items) → archivo (files) → objeto en S3 (bucket + s3_key)
```

> Hoy los cuatro agentes son **stubs**: devuelven siempre los mismos datos de ejemplo (marcados `[Ejemplo]`)
> que apuntan a los documentos 1, 2 y 3. Sirven para construir y probar la UI mientras se conectan los agentes
> reales ([sección 5](#5-implementar-los-agentes-reales)).

---

## 2. Endpoints

### 2.1 Salud

| Método | Ruta          | Qué hace                                                                 |
|--------|---------------|--------------------------------------------------------------------------|
| GET    | `/health`     | Responde `{"status":"ok"}` si la API está viva. No toca la BD ni S3.     |
| GET    | `/health/db`  | Ejecuta `SELECT 1` en PostgreSQL. **503** si no hay conexión.            |
| GET    | `/health/s3`  | Comprueba el acceso al bucket (`head_bucket`). **503** si falla.         |

### 2.2 Documentos (`/items`)

Cada documento es una norma SBS o una política interna. Sus archivos (PDF, etc.) se cargan aparte en `/files`.

| Método | Ruta                  | Qué hace                                                                                       |
|--------|-----------------------|------------------------------------------------------------------------------------------------|
| POST   | `/items`              | Crea un documento. **201** con el documento creado.                                             |
| GET    | `/items`              | Lista documentos por id (`skip`, `limit` hasta 500).                                            |
| GET    | `/items/{id}`         | Devuelve un documento. **404** si no existe.                                                    |
| GET    | `/items/{id}/files`   | Lista los archivos del documento (registros que apuntan a S3).                                  |
| PATCH  | `/items/{id}`         | Actualiza solo los campos enviados.                                                             |
| DELETE | `/items/{id}`         | Borra el documento, los registros de sus archivos y los objetos en S3. **204**.                 |

Campos del documento:

| Campo            | Tipo                         | Notas                                                                 |
|------------------|------------------------------|-----------------------------------------------------------------------|
| `name`           | texto (obligatorio)          | Nombre de la norma o política                                         |
| `description`    | texto                        |                                                                       |
| `is_active`      | booleano                     | Por defecto `true`                                                    |
| `tipo`           | `SBS` \| `POLITICA_INTERNA`  | Opcional                                                              |
| `codigo_norma`   | texto                        | Ej. el número de resolución                                           |
| `fecha_vigencia` | fecha `YYYY-MM-DD`           | Desde cuándo rige                                                     |
| `estado`         | `VIGENTE` \| `DEROGADA`      | Por defecto `VIGENTE`                                                 |
| `reemplaza_a`    | id de otro documento         | El documento que este reemplaza. `null` en un PATCH quita la relación |

Validaciones: `tipo` o `estado` fuera de los valores permitidos → **422**; `reemplaza_a` inexistente → **404**;
un documento que se reemplaza a sí mismo → **422**; `name`, `is_active` o `estado` en `null` en un PATCH → **422**.

```bash
curl -X POST $API/items -H "Content-Type: application/json" -d '{
  "name": "Reglamento de Gestión de Riesgo Operacional",
  "tipo": "SBS", "codigo_norma": "SBS-EJ-2020", "fecha_vigencia": "2020-03-15"
}'
```

```json
{
  "id": 1, "name": "Reglamento de Gestión de Riesgo Operacional", "description": null, "is_active": true,
  "tipo": "SBS", "codigo_norma": "SBS-EJ-2020", "fecha_vigencia": "2020-03-15",
  "estado": "VIGENTE", "reemplaza_a": null,
  "created_at": "2026-10-17T18:50:00Z", "updated_at": "2026-10-17T18:50:00Z"
}
```

### 2.3 Archivos (`/files`)

Cada archivo se guarda en S3 y la tabla `files` guarda un registro que apunta a él. La BD nunca queda
apuntando a un objeto que no existe (ver el [README](../README.md#consistencia-entre-s3-y-la-bd)).

| Método | Ruta                          | Qué hace                                                                                     |
|--------|-------------------------------|----------------------------------------------------------------------------------------------|
| POST   | `/files`                      | Sube un archivo (multipart: `file`, `item_id` opcional para asociarlo a un documento). **201**. |
| GET    | `/files`                      | Lista registros (`item_id` para filtrar por documento, `skip`, `limit`).                     |
| GET    | `/files/{id}`                 | Devuelve el registro: nombre original, tipo, tamaño, `bucket`, `s3_key`.                      |
| GET    | `/files/{id}/download`        | Descarga el archivo desde S3 pasando por la API, con su nombre original.                     |
| GET    | `/files/{id}/presigned-url`   | URL temporal para descargar directo desde S3 (`expires_in`, 60 s a 7 días). Ideal para la UI. |
| PUT    | `/files/{id}`                 | Reemplaza el contenido (se sube con una key nueva y se borra la anterior).                   |
| PATCH  | `/files/{id}`                 | Cambia `original_filename` o `item_id` (`null` lo desvincula del documento).                  |
| DELETE | `/files/{id}`                 | Borra el registro y el objeto en S3. **204**.                                                |

```bash
curl -X POST $API/files -F "file=@reglamento.pdf;type=application/pdf" -F "item_id=1"
```

### 2.4 Consultas (asistente normativo)

#### `POST /consultas`: hacer una pregunta

Registra la pregunta, lanza el pipeline en segundo plano y **responde de inmediato** (no espera a los agentes).

| Campo       | Obligatorio | Notas                                                                        |
|-------------|-------------|------------------------------------------------------------------------------|
| `pregunta`  | sí          | 1 a 4000 caracteres; se recortan espacios al inicio y al final               |
| `sesion_id` | no          | UUID de la conversación. Si no viene, se crea una sesión nueva               |

```bash
curl -X POST $API/consultas -H "Content-Type: application/json" \
  -d '{"pregunta": "¿Cuál es el plazo para reportar eventos de pérdida?"}'
```

Respuesta **202 Accepted**:

```json
{
  "ejecucion_id": "d034da04-b78e-4d98-8859-448941e3cd16",
  "sesion_id": "84b033e3-9ffe-4dc2-ba63-433d6d8aa626",
  "estado": "PENDIENTE"
}
```

Guarda `sesion_id` en la UI y envíalo en las siguientes preguntas para agruparlas en la misma conversación.
Errores: pregunta vacía, `sesion_id` que no es UUID → **422**.

#### `GET /consultas/{ejecucion_id}`: ver el avance o el resultado

Devuelve la ejecución con sus pasos ordenados. La UI lo consulta cada 1-2 s hasta que `estado` sea
`COMPLETADO` o `ERROR`. **404** si no existe; **422** si el id no es UUID.

Ejemplo real de una consulta terminada (salidas de los stubs, recortadas):

```json
{
  "id": "d034da04-b78e-4d98-8859-448941e3cd16",
  "sesion_id": "84b033e3-9ffe-4dc2-ba63-433d6d8aa626",
  "pregunta": "¿Cuál es el plazo para reportar eventos de pérdida?",
  "estado": "COMPLETADO",
  "paso_actual": null,
  "respuesta": "[Respuesta de ejemplo] Sobre «¿Cuál es el plazo...?»: según Artículo 5 del documento 1; Numeral 4.2 del documento 3, el plazo aplicable es de 30 días calendario. Ojo: hay diferencias con la política interna; revisa las alertas.",
  "creado_en": "2026-10-17T18:55:31.295076Z",
  "actualizado_en": "2026-10-17T18:55:35.387259Z",
  "pasos": [
    {
      "id": "84706e19-...", "agente": "BUSCADOR", "orden": 1, "estado": "COMPLETADO",
      "duracion_ms": 1000, "error": null, "creado_en": "2026-10-17T18:55:32.345966Z",
      "salida": {"articulos": [
        {"documento_id": 1, "articulo": "Artículo 5", "fragmento": "...30 días calendario.", "score": 0.92},
        {"documento_id": 2, "articulo": "Artículo 12", "fragmento": "...60 días.", "score": 0.85},
        {"documento_id": 3, "articulo": "Numeral 4.2", "fragmento": "...45 días.", "score": 0.78}
      ]}
    },
    {
      "agente": "VIGENCIA", "orden": 2, "estado": "COMPLETADO", "duracion_ms": 1000,
      "salida": {
        "vigentes": [{"documento_id": 1, "...": "..."}, {"documento_id": 3, "...": "..."}],
        "descartados": [{"documento_id": 2, "motivo": "Norma derogada", "reemplazado_por": 1}]
      }
    },
    {
      "agente": "CONFLICTOS", "orden": 3, "estado": "COMPLETADO", "duracion_ms": 1000,
      "salida": {"conflictos": [{"documento_a": 1, "documento_b": 3,
        "tema": "Plazo de reporte de eventos de pérdida",
        "descripcion": "Artículo 5 fija 30 días y Numeral 4.2 fija 45 días."}]}
    },
    {
      "agente": "REDACTOR", "orden": 4, "estado": "COMPLETADO", "duracion_ms": 1000,
      "salida": {
        "respuesta": "...",
        "citas": [{"documento_id": 1, "articulo": "Artículo 5"}, {"documento_id": 3, "articulo": "Numeral 4.2"}],
        "alertas": [
          {"tipo": "CONFLICTO", "mensaje": "Plazo de reporte de eventos de pérdida: ..."},
          {"tipo": "VIGENCIA", "mensaje": "El documento 2 no está vigente (Norma derogada); reemplazado por el documento 1."}
        ]
      }
    }
  ]
}
```

> PostgreSQL guarda `salida` como JSONB y puede devolver las claves en otro orden; léelas por nombre.

Qué mostrar en la UI con este JSON:

| Mientras corre (`EN_PROCESO`)                       | Al terminar (`COMPLETADO`)                                       | Si falla (`ERROR`)                                  |
|-----------------------------------------------------|------------------------------------------------------------------|-----------------------------------------------------|
| Barra de 4 pasos; resalta `paso_actual`; los pasos ya en `pasos` van con ✓ y su `duracion_ms` | `respuesta`; las `citas` y `alertas` del paso REDACTOR; los artículos de BUSCADOR como fuentes | El paso con `estado: ERROR` y su `error`; ofrecer reintentar (otro `POST`) |

#### `GET /sesiones/{sesion_id}/consultas`: historial de la conversación

Lista las consultas de la sesión, **la más reciente primero**, sin los pasos (para eso está
`GET /consultas/{id}`). Acepta `limit` (1-200, por defecto 50). Una sesión sin consultas devuelve `[]`.

```json
[
  {"id": "…", "sesion_id": "84b033e3-…", "pregunta": "¿Y para eventos menores?", "estado": "EN_PROCESO",
   "paso_actual": "VIGENCIA", "respuesta": null, "creado_en": "…", "actualizado_en": "…"},
  {"id": "d034da04-…", "sesion_id": "84b033e3-…", "pregunta": "¿Cuál es el plazo para reportar eventos de pérdida?",
   "estado": "COMPLETADO", "paso_actual": null, "respuesta": "…", "creado_en": "…", "actualizado_en": "…"}
]
```

---

## 3. El proceso de una consulta, paso a paso

### Estados de la ejecución

```
PENDIENTE ──► EN_PROCESO (BUSCADOR) ──► EN_PROCESO (VIGENCIA) ──► EN_PROCESO (CONFLICTOS) ──► EN_PROCESO (REDACTOR) ──► COMPLETADO
                    │                         │                          │                           │
                    └─────────────────────────┴──────────────────────────┴───────────────────────────┴──► ERROR
```

### Qué se escribe en la BD en cada momento

| Momento                         | `ejecucion`                                              | `paso_agente`                                                   |
|---------------------------------|----------------------------------------------------------|-----------------------------------------------------------------|
| `POST /consultas`               | Nueva fila: `estado=PENDIENTE`, `paso_actual=null`       | —                                                               |
| Antes de cada agente            | `paso_actual=<agente>`, `estado=EN_PROCESO`              | —                                                               |
| El agente terminó bien          | —                                                        | Nueva fila: `estado=COMPLETADO`, `salida`, `duracion_ms`, `orden` |
| El agente falló                 | `estado=ERROR` (`paso_actual` queda en ese agente)       | Nueva fila: `estado=ERROR`, `error="Tipo: mensaje"`, `salida=null` |
| Terminó el REDACTOR             | `respuesta=<texto>`, `estado=COMPLETADO`, `paso_actual=null` | —                                                           |

Cada cambio se confirma (commit) en el momento, por eso el polling ve el avance en vivo.

### Cuándo un agente "falla"

- Lanza cualquier excepción (timeout del LLM, error de red, un `KeyError`, etc.).
- Devuelve algo que **no cumple su contrato** ([`app/agentes/contratos.py`](../app/agentes/contratos.py)): falta un
  campo, un tipo es incorrecto o un valor no está permitido. El `error` del paso dice qué campo falló.

En ambos casos el pipeline se detiene, los agentes siguientes no corren y **la API sigue funcionando**.

### Lo que el diseño no cubre (por ahora)

- Si la API se reinicia a mitad de un pipeline, esa ejecución queda en `EN_PROCESO` y no se retoma.
- El pipeline corre dentro del mismo proceso de la API (BackgroundTasks, sin colas). Para la demo es suficiente;
  con mucho tráfico conviene una cola de trabajos.

### Auditar una respuesta con SQL

```sql
-- Qué artículos citó cada consulta de una sesión, y de qué documento y archivo salen
SELECT e.pregunta, cita->>'articulo' AS articulo, d.name AS documento, d.estado, f.original_filename, f.s3_key
FROM ejecucion e
JOIN paso_agente p ON p.ejecucion_id = e.id AND p.agente = 'REDACTOR'
CROSS JOIN LATERAL jsonb_array_elements(p.salida->'citas') AS cita
JOIN items d ON d.id = (cita->>'documento_id')::int
LEFT JOIN files f ON f.item_id = d.id
WHERE e.sesion_id = '84b033e3-9ffe-4dc2-ba63-433d6d8aa626'
ORDER BY e.creado_en DESC;
```

---

## 4. Casos de uso

Los tres casos usan la misma base de documentos. Suponemos que al cargarlos quedan con ids 1, 2 y 3, que son
los que usan los stubs; con agentes reales los ids salen de la BD.

**Preparación** (una sola vez):

```bash
# 1. Norma SBS vigente
curl -X POST $API/items -H "Content-Type: application/json" -d '{
  "name": "Reglamento de Gestión de Riesgo Operacional (2020)", "tipo": "SBS",
  "codigo_norma": "SBS-EJ-2020", "fecha_vigencia": "2020-03-15"}'          # → id 1

# 2. Norma SBS anterior, ya derogada
curl -X POST $API/items -H "Content-Type: application/json" -d '{
  "name": "Reglamento de Gestión de Riesgo Operacional (2009)", "tipo": "SBS",
  "codigo_norma": "SBS-EJ-2009", "fecha_vigencia": "2009-07-01", "estado": "DEROGADA"}'   # → id 2

# 3. Política interna del banco
curl -X POST $API/items -H "Content-Type: application/json" -d '{
  "name": "Política de Gestión de Eventos de Pérdida", "tipo": "POLITICA_INTERNA",
  "codigo_norma": "POL-RO-004", "fecha_vigencia": "2023-01-10"}'           # → id 3

# La norma 2020 reemplaza a la de 2009
curl -X PATCH $API/items/1 -H "Content-Type: application/json" -d '{"reemplaza_a": 2}'

# Los PDF de cada documento
curl -X POST $API/files -F "file=@reglamento_2020.pdf;type=application/pdf" -F "item_id=1"
curl -X POST $API/files -F "file=@reglamento_2009.pdf;type=application/pdf" -F "item_id=2"
curl -X POST $API/files -F "file=@politica_eventos_perdida.pdf;type=application/pdf" -F "item_id=3"
```

### Caso 1: respuesta citada y trazable hasta el PDF

**Situación.** Un analista de riesgos pregunta el plazo de reporte y necesita poder mostrar de dónde sale la
respuesta.

1. **Pregunta** → `POST /consultas` con `{"pregunta": "¿Cuál es el plazo para reportar a la SBS un evento de pérdida significativo?"}`.
   Recibe `ejecucion_id` y `sesion_id` en milisegundos.
2. **Polling** → `GET /consultas/{ejecucion_id}` cada segundo. La UI muestra el avance:

   | t     | `estado`   | `paso_actual` | pasos guardados |
   |-------|------------|---------------|-----------------|
   | 0.3 s | EN_PROCESO | BUSCADOR      | 0               |
   | 1.4 s | EN_PROCESO | VIGENCIA      | 1               |
   | 2.5 s | EN_PROCESO | CONFLICTOS    | 2               |
   | 3.6 s | EN_PROCESO | REDACTOR      | 3               |
   | 4.8 s | COMPLETADO | `null`        | 4               |

3. **Respuesta** → `respuesta` del ejecución y, en el paso REDACTOR, la cita
   `{"documento_id": 1, "articulo": "Artículo 5"}`.
4. **Ir a la fuente** → con el `documento_id` de la cita:

   ```bash
   curl $API/items/1                    # Reglamento ... (2020), SBS, VIGENTE
   curl $API/items/1/files              # [{"id": 7, "original_filename": "reglamento_2020.pdf", "s3_key": "uploads/…pdf", …}]
   curl $API/files/7/presigned-url      # {"url": "https://…s3.amazonaws.com/…", "expires_in": 3600}
   ```

   La UI pone un botón **"Ver artículo"** que abre esa URL: el analista llega al PDF exacto.

**Qué demuestra:** la cadena pregunta → agente → artículo → documento → archivo → S3 completa, sin guardar nada
extra: todo sale de `paso_agente.salida` y de las tablas existentes.

### Caso 2: la norma encontrada está derogada

**Situación.** El buscador encuentra un artículo de la norma de 2009, que ya fue reemplazada. El analista no debe
recibir un plazo derogado como respuesta.

Lo que deben producir los agentes (los stubs ya lo simulan así):

```json
// BUSCADOR: encuentra artículos en las dos versiones de la norma
{"articulos": [
  {"documento_id": 1, "articulo": "Artículo 5",  "fragmento": "…dentro de los 30 días calendario.", "score": 0.92},
  {"documento_id": 2, "articulo": "Artículo 12", "fragmento": "…en un plazo de 60 días.",          "score": 0.85}
]}

// VIGENCIA: mira items.estado y items.reemplaza_a y descarta la 2009
{"vigentes": [{"documento_id": 1, "articulo": "Artículo 5", "fragmento": "…", "score": 0.92}],
 "descartados": [{"documento_id": 2, "motivo": "Norma derogada", "reemplazado_por": 1}]}

// REDACTOR: responde solo con lo vigente y avisa
{"respuesta": "El plazo es de 30 días calendario (Artículo 5 del Reglamento 2020)…",
 "citas": [{"documento_id": 1, "articulo": "Artículo 5"}],
 "alertas": [{"tipo": "VIGENCIA", "mensaje": "El Reglamento 2009 (Art. 12, 60 días) está derogado; lo reemplaza el Reglamento 2020."}]}
```

**En la UI:** la respuesta usa 30 días y una alerta amarilla **VIGENCIA** explica por qué no se usó el artículo de 60
días. Para que VIGENCIA funcione con datos reales, mantén actualizados `estado`, `fecha_vigencia` y `reemplaza_a`
en `/items` (es lo que se cargó en la preparación).

### Caso 3: la política interna contradice a la norma SBS (y se sigue conversando)

**Situación.** La política interna da 45 días a las áreas para reportar, pero la SBS exige reportar en 30. El
asistente debe advertirlo. Luego el analista hace una pregunta de seguimiento en la misma conversación.

```json
// CONFLICTOS: compara los artículos vigentes de distinto documento
{"conflictos": [{
  "documento_a": 1, "documento_b": 3,
  "tema": "Plazo de reporte de eventos de pérdida",
  "descripcion": "La norma SBS (Art. 5) exige 30 días; la política interna (Num. 4.2) permite 45 días a las áreas."
}]}

// REDACTOR
{"respuesta": "Ante la SBS el plazo es 30 días. La política interna permite 45 días para el reporte interno, lo que deja poco margen…",
 "citas": [{"documento_id": 1, "articulo": "Artículo 5"}, {"documento_id": 3, "articulo": "Numeral 4.2"}],
 "alertas": [{"tipo": "CONFLICTO", "mensaje": "La Política POL-RO-004 (45 días) no es compatible con el plazo SBS (30 días)."}]}
```

**Seguimiento en la misma sesión:**

```bash
curl -X POST $API/consultas -H "Content-Type: application/json" -d '{
  "sesion_id": "84b033e3-9ffe-4dc2-ba63-433d6d8aa626",
  "pregunta": "¿Qué área debería actualizar la política?"}'

curl $API/sesiones/84b033e3-9ffe-4dc2-ba63-433d6d8aa626/consultas   # las dos preguntas, la más nueva primero
```

**En la UI:** alerta roja **CONFLICTO** con los dos documentos enlazados (cada uno a su PDF, como en el caso 1) y el
historial de la conversación a la izquierda, armado con `GET /sesiones/{sesion_id}/consultas`.

> Hoy cada consulta es independiente: los agentes no reciben las preguntas anteriores de la sesión. Si quieren que
> el REDACTOR tenga en cuenta la conversación, el agente puede leer el historial de la sesión desde la BD
> (ver la sección 5.4, VIGENCIA, para el patrón de acceso a la BD).

### ¿Y si un agente falla?

Si, por ejemplo, CONFLICTOS no logra conectarse al LLM:

```json
{
  "estado": "ERROR", "paso_actual": "CONFLICTOS", "respuesta": null,
  "pasos": [
    {"agente": "BUSCADOR",   "estado": "COMPLETADO", "...": "..."},
    {"agente": "VIGENCIA",   "estado": "COMPLETADO", "...": "..."},
    {"agente": "CONFLICTOS", "estado": "ERROR", "salida": null, "duracion_ms": 30012,
     "error": "APITimeoutError: Request timed out."}
  ]
}
```

La UI muestra en qué paso falló y ofrece reintentar (un nuevo `POST /consultas` con la misma pregunta y `sesion_id`).

---

## 5. Implementar los agentes reales

### 5.1 El contrato que no cambia

Cada agente es una función en `app/agentes/<agente>.py`:

```python
def conflictos(pregunta: str, contexto_previo: dict) -> dict: ...
```

- **`contexto_previo`** trae la salida de los agentes anteriores por nombre: el BUSCADOR recibe `{}`, la VIGENCIA
  recibe `{"BUSCADOR": {...}}`, la CONFLICTOS recibe `{"BUSCADOR": ..., "VIGENCIA": ...}` y así.
- **Lo que devuelve** tiene que cumplir su modelo en [`app/agentes/contratos.py`](../app/agentes/contratos.py)
  (`SalidaBuscador`, `SalidaVigencia`, `SalidaConflictos`, `SalidaRedactor`). El orquestador lo valida.
- **No hace falta `try/except`**: cualquier excepción deja el paso en `ERROR` con el mensaje.
- **Quita la llamada a `simular_trabajo()`**: solo existe para que los stubs tarden en la demo.
- **No toques el orquestador ni los endpoints**: cambiar un agente es cambiar el cuerpo de su función.

### 5.2 ¿Un agente o varios?

| Enfoque | Cómo es | A favor | En contra | Recomendado para |
|---------|---------|---------|-----------|------------------|
| **A. Un modelo, cuatro roles** | Las 4 funciones llaman al mismo LLM, cada una con su prompt y su contrato | Lo más rápido de implementar; un solo cliente y un solo helper | VIGENCIA queda en manos del LLM, que puede equivocarse con fechas y estados | La demo de hoy |
| **B. Agentes especializados** | Cada agente usa la herramienta adecuada: BUSCADOR lee los documentos, **VIGENCIA es SQL sin LLM**, CONFLICTOS y REDACTOR usan el LLM | Más confiable y barato: la vigencia sale de la BD, no de una interpretación | Un poco más de código | Lo que conviene después de la demo |
| **C. Un solo agente con herramientas** | Un LLM con tools (`buscar`, `ver_vigencia`…) que decide todo en un loop | Flexible para preguntas abiertas | Se pierde el paso a paso: la UI y `paso_agente` verían un solo paso | No encaja con este diseño; úsalo, si acaso, **dentro** del BUSCADOR (5.5) |

La recomendación es **empezar con A para la demo y pasar VIGENCIA a SQL (B) en cuanto se pueda**. Como cada agente
es una función independiente, se pueden mezclar: unos con LLM y otros sin él.

### 5.3 Preparación: SDK, clave y helper común

1. **Dependencia** (la única nueva): agrega `anthropic` a `requirements.txt` e instálala.

   ```bash
   pip install anthropic
   ```

2. **Clave en la configuración.** La app lee el `.env` con pydantic-settings, que **no** lo copia a las
   variables de entorno; por eso la clave se pasa explícitamente al cliente. En `app/core/config.py`:

   ```python
   # Agentes (LLM)
   anthropic_api_key: str | None = None
   agent_model: str = "claude-opus-5-5"
   ```

   y en el `.env`: `ANTHROPIC_API_KEY=sk-ant-...`. El script de despliegue ya copia el `.env` (sin las keys de
   AWS) a Parameter Store, así que la clave llega sola a la EC2.

3. **Helper común** `app/agentes/llm.py`: una llamada que devuelve JSON ya validado contra el contrato.

   ```python
   from functools import lru_cache
   from typing import Any

   import anthropic
   from pydantic import BaseModel

   from app.core.config import get_settings


   @lru_cache
   def _client() -> anthropic.Anthropic:
       return anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=120.0)


   def pedir_json(system: str, content: str | list[dict[str, Any]], contrato: type[BaseModel]) -> dict[str, Any]:
       """Llama al modelo con salida estructurada y devuelve el dict validado contra `contrato`."""
       response = _client().beta.messages.parse(
           model=get_settings().agent_model,
           max_tokens=16000,
           # Si el modelo rechaza por seguridad, la API reintenta con otro modelo recomendado
           betas=["server-side-fallback-2026-07-01"],
           fallbacks="default",
           system=system,
           messages=[{"role": "user", "content": content}],
           output_format=contrato,
       )
       if response.stop_reason == "refusal":
           categoria = response.stop_details.category if response.stop_details else None
           raise RuntimeError(f"El modelo rechazó la solicitud (categoría: {categoria})")
       if response.parsed_output is None:
           raise RuntimeError(f"Respuesta sin JSON válido (stop_reason={response.stop_reason})")
       return response.parsed_output.model_dump()
   ```

   - `output_format=contrato` hace que el modelo responda exactamente con la forma del modelo Pydantic; el
     orquestador lo vuelve a validar igual.
   - `fallbacks="default"`: si el modelo rechaza la consulta por sus filtros de seguridad, la API la reintenta
     sola con un modelo alternativo recomendado. Si no lo quieren, quiten `betas` y `fallbacks`.
   - Las excepciones del SDK (timeout, límite de uso, red) no se capturan a propósito: el orquestador las registra
     como `ERROR` del paso. El SDK ya reintenta 2 veces los errores 429 y 5xx.

### 5.4 Ejemplo por agente

#### BUSCADOR: el modelo lee los PDF de los documentos vigentes

Para empezar sin índices ni embeddings: se mandan al modelo los PDF de los documentos (desde S3) y se le pide
que devuelva los artículos relevantes con su `documento_id`. Sirve mientras los documentos entren en una
solicitud (hasta 32 MB y 600 páginas en total).

```python
import base64
from typing import Any

from sqlalchemy import select

from app.agentes.contratos import SalidaBuscador
from app.agentes.llm import pedir_json
from app.db import session as db_session
from app.models.file import FileRecord
from app.models.item import Item
from app.services.s3 import get_s3_service

SYSTEM = (
    "Eres un analista de cumplimiento normativo bancario en Perú. Recibes normas SBS y políticas internas, "
    "cada una precedida por su documento_id. Devuelve los artículos o numerales que responden la pregunta, "
    "con el texto literal en 'fragmento' y un 'score' de 0 a 1 según su relevancia. "
    "Usa solo los documento_id indicados. Si nada responde la pregunta, devuelve una lista vacía."
)


def buscador(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    s3 = get_s3_service()
    content: list[dict[str, Any]] = []
    with db_session.SessionLocal() as db:
        documentos = db.scalars(select(Item).where(Item.tipo.is_not(None))).all()
        for doc in documentos:
            pdfs = db.scalars(
                select(FileRecord).where(FileRecord.item_id == doc.id, FileRecord.content_type == "application/pdf")
            ).all()
            for pdf in pdfs:
                chunks, _ = s3.download(pdf.s3_key, bucket=pdf.bucket)
                data = base64.standard_b64encode(b"".join(chunks)).decode()
                content.append({"type": "text", "text": f"documento_id={doc.id}: {doc.name} ({doc.codigo_norma}), "
                                                        f"tipo {doc.tipo}, estado {doc.estado}"})
                content.append({"type": "document",
                                "source": {"type": "base64", "media_type": "application/pdf", "data": data}})
    content.append({"type": "text", "text": f"Pregunta del analista: {pregunta}"})
    return pedir_json(SYSTEM, content, SalidaBuscador)
```

Se incluyen también los documentos derogados a propósito: decidir qué se descarta es tarea de VIGENCIA.

Cuando los documentos sean muchos o muy grandes, el siguiente paso es extraer el texto al subir cada PDF,
partirlo por artículos e indexarlo (por ejemplo con búsqueda de texto completo de PostgreSQL o embeddings);
el BUSCADOR entonces envía al modelo solo los fragmentos candidatos. La firma y el contrato no cambian.

#### VIGENCIA: SQL, sin LLM (enfoque B)

La vigencia ya está en la BD (`estado`, `fecha_vigencia`, `reemplaza_a`), así que se decide con una consulta: es
exacta, instantánea y gratis.

```python
from datetime import date
from typing import Any

from sqlalchemy import select

from app.db import session as db_session
from app.models.item import Item


def vigencia(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    articulos = contexto_previo["BUSCADOR"]["articulos"]
    ids = {a["documento_id"] for a in articulos}
    with db_session.SessionLocal() as db:
        documentos = {d.id: d for d in db.scalars(select(Item).where(Item.id.in_(ids)))}
        # documento reemplazado -> documento que lo reemplaza
        reemplazos = {d.reemplaza_a: d.id for d in db.scalars(select(Item).where(Item.reemplaza_a.in_(ids)))}

    vigentes, descartados = [], []
    for articulo in articulos:
        doc_id = articulo["documento_id"]
        doc = documentos.get(doc_id)
        if doc is None:
            motivo = "El documento no existe"
        elif doc.estado == "DEROGADA":
            motivo = "Norma derogada"
        elif doc_id in reemplazos:
            motivo = "Reemplazada por una norma posterior"
        elif doc.fecha_vigencia and doc.fecha_vigencia > date.today():
            motivo = f"Aún no entra en vigencia (rige desde {doc.fecha_vigencia:%d/%m/%Y})"
        else:
            vigentes.append(articulo)
            continue
        descartados.append({"documento_id": doc_id, "motivo": motivo, "reemplazado_por": reemplazos.get(doc_id)})
    return {"vigentes": vigentes, "descartados": descartados}
```

> Se importa el **módulo** `app.db.session` (no `SessionLocal` directamente) para que los tests puedan
> reemplazar `app.db.session.SessionLocal` por una base SQLite.

Si prefieren el enfoque A para la demo, VIGENCIA puede llamar a `pedir_json` con los artículos y los datos de cada
documento, igual que CONFLICTOS.

#### CONFLICTOS: el modelo compara los artículos vigentes

```python
import json
from typing import Any

from app.agentes.contratos import SalidaConflictos
from app.agentes.llm import pedir_json

SYSTEM = (
    "Eres un auditor de cumplimiento normativo bancario en Perú. Recibes artículos vigentes de normas SBS y de "
    "políticas internas. Identifica contradicciones reales entre artículos de documentos distintos (plazos, montos, "
    "responsables, requisitos), indicando ambos documento_id, el tema y una descripción breve y concreta. "
    "No reportes diferencias de redacción que no cambian la obligación. Si no hay contradicciones, devuelve una lista vacía."
)


def conflictos(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    vigentes = contexto_previo["VIGENCIA"]["vigentes"]
    if len({a["documento_id"] for a in vigentes}) < 2:
        return {"conflictos": []}  # sin dos documentos distintos no puede haber conflicto
    prompt = (
        f"Pregunta del analista: {pregunta}\n\n"
        f"Artículos vigentes (JSON):\n{json.dumps(vigentes, ensure_ascii=False, indent=2)}"
    )
    return pedir_json(SYSTEM, prompt, SalidaConflictos)
```

#### REDACTOR: el modelo escribe la respuesta con citas y alertas

```python
import json
from typing import Any

from app.agentes.contratos import SalidaRedactor
from app.agentes.llm import pedir_json

SYSTEM = (
    "Eres un asistente para analistas bancarios en Perú. Responde la pregunta en español claro y breve usando "
    "solo los artículos vigentes que recibes. En 'citas' incluye cada artículo que usaste (documento_id y "
    "articulo). En 'alertas' agrega una de tipo CONFLICTO por cada contradicción recibida y una de tipo VIGENCIA "
    "por cada documento descartado que el analista podría estar usando por error. Si los artículos no alcanzan "
    "para responder, dilo explícitamente en lugar de suponer."
)


def redactor(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    datos = {
        "vigentes": contexto_previo["VIGENCIA"]["vigentes"],
        "descartados": contexto_previo["VIGENCIA"]["descartados"],
        "conflictos": contexto_previo["CONFLICTOS"]["conflictos"],
    }
    prompt = f"Pregunta del analista: {pregunta}\n\nInsumos (JSON):\n{json.dumps(datos, ensure_ascii=False, indent=2)}"
    return pedir_json(SYSTEM, prompt, SalidaRedactor)
```

### 5.5 Opcional: BUSCADOR como agente con herramientas

Si el modelo debe decidir qué buscar (varias búsquedas, refinar términos), se le pueden dar herramientas con el
Tool Runner del SDK, que maneja el loop de llamadas. El resultado final se sigue pidiendo con el contrato:

```python
import json
from typing import Any

from anthropic import beta_tool
from sqlalchemy import or_, select

from app.agentes.contratos import SalidaBuscador
from app.agentes.llm import _client
from app.core.config import get_settings
from app.db import session as db_session
from app.models.item import Item


@beta_tool
def buscar_documentos(texto: str) -> str:
    """Busca normas SBS y políticas internas por nombre, descripción o código.

    Args:
        texto: Palabras clave, por ejemplo "eventos de pérdida" o "SBS-EJ-2020".
    """
    patron = f"%{texto}%"
    with db_session.SessionLocal() as db:
        docs = db.scalars(select(Item).where(or_(
            Item.name.ilike(patron), Item.description.ilike(patron), Item.codigo_norma.ilike(patron)
        )).limit(10)).all()
    return json.dumps([{"documento_id": d.id, "nombre": d.name, "codigo": d.codigo_norma,
                        "tipo": d.tipo, "estado": d.estado} for d in docs], ensure_ascii=False)


def buscador(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    runner = _client().beta.messages.tool_runner(
        model=get_settings().agent_model,
        max_tokens=16000,
        max_iterations=6,
        system="Busca los artículos que responden la pregunta del analista usando las herramientas.",
        tools=[buscar_documentos],
        messages=[{"role": "user", "content": pregunta}],
        output_format=SalidaBuscador,
    )
    final = runner.until_done()
    if final.parsed_output is None:
        raise RuntimeError(f"El buscador no devolvió artículos válidos (stop_reason={final.stop_reason})")
    return final.parsed_output.model_dump()
```

Una segunda herramienta, `leer_documento(documento_id)`, puede devolver el texto del documento para que el
modelo extraiga los fragmentos. Un consejo: empiecen por el BUSCADOR de 5.4, que es más simple y predecible.

### 5.6 Tiempos, costos y modelo

- **Tiempos:** con el LLM cada agente tarda segundos, no milisegundos. La UI ya está preparada: hace polling y
  muestra el avance. El `timeout=120.0` del cliente evita que un paso quede colgado.
- **Modelo:** `claude-opus-5-5` por defecto (configurable con `AGENT_MODEL` en el `.env`). Para bajar costo,
  pueden probar `claude-sonnet-5-5` en los agentes y comparar las respuestas con las mismas preguntas.
- **Concurrencia:** cada consulta corre en un hilo del servidor (hasta 40 a la vez por defecto). Para la demo
  sobra.

### 5.7 Tests sin llamar al LLM

Los tests no deben llamar al modelo (lento, con costo y no determinista). El patrón ya está en
[`tests/test_consultas.py`](../tests/test_consultas.py): reemplazar el agente en `orquestador.PIPELINE` con
`monkeypatch` por una función que devuelve datos fijos.

```python
def test_redactor_recibe_conflictos(client, monkeypatch):
    def redactor_falso(pregunta, contexto_previo):
        assert contexto_previo["CONFLICTOS"]["conflictos"]
        return {"respuesta": "ok", "citas": [], "alertas": []}

    _replace_agent(monkeypatch, Agente.REDACTOR, redactor_falso)
    ...
```

Para probar un agente que usa la BD (como VIGENCIA en SQL), reemplaza `app.db.session.SessionLocal` por la fábrica
SQLite del fixture `session_factory`.

### 5.8 Lista de verificación

- [ ] `anthropic` en `requirements.txt`; `ANTHROPIC_API_KEY` en el `.env`; `anthropic_api_key` y `agent_model` en `Settings`.
- [ ] `app/agentes/llm.py` con `pedir_json`.
- [ ] Reemplazar el cuerpo de cada agente y quitar `simular_trabajo()`.
- [ ] Probar en local: `POST /consultas` y revisar `pasos[].salida` y `pasos[].error`.
- [ ] `pytest` sigue pasando (los tests usan agentes falsos).
- [ ] Desplegar: `bash scripts/aws_deploy_ec2.sh`.

---

## 6. Agregar o cambiar agentes del pipeline

El orden del pipeline está en `PIPELINE` de [`app/services/orquestador.py`](../app/services/orquestador.py). Para
agregar un agente (por ejemplo un `VERIFICADOR` después del REDACTOR):

1. Agrega el valor a `Agente` en [`app/models/enums.py`](../app/models/enums.py).
2. Crea una migración `migrations/0003_agente_verificador.sql` que amplíe los dos `CHECK` que validan el nombre:

   ```sql
   ALTER TABLE ejecucion DROP CONSTRAINT ck_ejecucion_paso_actual;
   ALTER TABLE ejecucion ADD CONSTRAINT ck_ejecucion_paso_actual
       CHECK (paso_actual IN ('BUSCADOR', 'VIGENCIA', 'CONFLICTOS', 'REDACTOR', 'VERIFICADOR'));
   ALTER TABLE paso_agente DROP CONSTRAINT ck_paso_agente_agente;
   ALTER TABLE paso_agente ADD CONSTRAINT ck_paso_agente_agente
       CHECK (agente IN ('BUSCADOR', 'VIGENCIA', 'CONFLICTOS', 'REDACTOR', 'VERIFICADOR'));
   ```

3. Define su contrato en `app/agentes/contratos.py` y su función en `app/agentes/verificador.py`.
4. Agrégalo a `PIPELINE` en el lugar que corresponda.
5. Si el nuevo agente pasa a ser el último, ajusta la línea del orquestador que toma la respuesta final
   (`contexto["REDACTOR"]["respuesta"]`).

La migración se aplica sola al desplegar (`bash scripts/aws_deploy_ec2.sh`) o con `python -m app.db.migrate`.
