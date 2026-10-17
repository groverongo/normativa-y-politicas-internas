# NttBanca API

API en FastAPI sobre PostgreSQL (AWS RDS) y S3 para el **asistente normativo SBS**: un analista hace una
pregunta y un pipeline de 4 agentes (BUSCADOR → VIGENCIA → CONFLICTOS → REDACTOR) responde citando normas SBS
y políticas internas, con alertas de contradicciones y normas derogadas.

- **Items (documentos)**: cada norma SBS o política interna, con tipo, código, vigencia, estado y qué
  documento reemplaza.
- **Files**: cada archivo se guarda en S3 y la tabla `files` guarda un registro que **apunta** al objeto
  (`bucket` + `s3_key`) junto con sus metadatos. Un archivo puede pertenecer a un documento o estar suelto.
- **Consultas**: cada pregunta queda en `ejecucion` y la salida de cada agente en `paso_agente`.

Trazabilidad completa: pregunta (`ejecucion`) → agente (`paso_agente`) → artículo (`salida`, con
`documento_id`) → documento (`items`) → archivo (`files`) → objeto en S3.

**Guía funcional:** qué hace cada endpoint, el proceso de una consulta, 3 casos de uso y cómo conectar los
agentes a un LLM → **[docs/ASISTENTE_NORMATIVO.md](docs/ASISTENTE_NORMATIVO.md)**.

## Tablas

```
items (documentos)                        files
─────────────────────────────────         ──────────────────────────────────────────
id             SERIAL  PK  ◄─┐  ◄────┐    id                 SERIAL   PK
name           VARCHAR(255)  │       └─── item_id            INTEGER  FK → items.id (ON DELETE CASCADE), nullable
description    TEXT          │            bucket             VARCHAR(63)   ┐ puntero al objeto en S3
is_active      BOOLEAN       │            s3_key             VARCHAR(1024) ┘ UNIQUE (bucket, s3_key)
tipo           SBS | POLITICA_INTERNA     original_filename  VARCHAR(255)
codigo_norma   TEXT          │            content_type       VARCHAR(255)
fecha_vigencia DATE          │            size_bytes         BIGINT
estado         VIGENTE | DEROGADA         etag               VARCHAR(255)
reemplaza_a    INTEGER ──────┘ FK → items.id (ON DELETE SET NULL), nullable
created_at / updated_at  TIMESTAMPTZ      created_at / updated_at  TIMESTAMPTZ

ejecucion                                 paso_agente
─────────────────────────────────         ──────────────────────────────────────────
id             UUID  PK  ◄─────────────── ejecucion_id  UUID  FK → ejecucion.id (ON DELETE CASCADE)
sesion_id      UUID                       id            UUID  PK
pregunta       TEXT                       agente        BUSCADOR | VIGENCIA | CONFLICTOS | REDACTOR
estado         PENDIENTE | EN_PROCESO |   orden         INT   UNIQUE (ejecucion_id, orden)
               COMPLETADO | ERROR         estado        COMPLETADO | ERROR
paso_actual    agente en curso, nullable  salida        JSONB (salida del agente)
respuesta      TEXT                       duracion_ms   INT
creado_en / actualizado_en  TIMESTAMPTZ   error         TEXT
                                          creado_en     TIMESTAMPTZ
```

### Migraciones

El esquema se versiona con archivos SQL en [`migrations/`](migrations/), aplicados por
[`app/db/migrate.py`](app/db/migrate.py) (sin dependencias extra). Cada archivo se aplica una sola vez, en orden,
dentro de una transacción, y queda registrado en la tabla `schema_migrations`.

```bash
python -m app.db.migrate --status    # aplicadas y pendientes (solo lectura)
python -m app.db.migrate --dry-run   # aplica y deshace, para probar
python -m app.db.migrate             # aplica las pendientes
```

Además se aplican solas al arrancar la API (`DB_AUTO_CREATE_TABLES=true`) y en cada despliegue a EC2. Para
cambiar el esquema, agrega un archivo nuevo (`0003_descripcion.sql`); no edites uno ya aplicado.

### Consistencia entre S3 y la BD

Un registro de `files` nunca apunta a un objeto inexistente:

- **Subir / reemplazar**: primero se sube a S3 y luego se guarda en la BD. Si la BD falla, se borra lo subido.
  Al reemplazar se usa una key nueva y el objeto anterior se borra solo después del commit.
- **Borrar** (un archivo o un item con sus archivos): primero la BD, luego S3. Si S3 falla, el objeto queda
  huérfano en el bucket y se registra en el log, pero ningún registro lo referencia.

Las keys se generan como `S3_KEY_PREFIX/<uuid>.<ext>`; el nombre original vive en la BD y se usa al descargar.

## Estructura

```
app/
├── main.py                  # crea la app, registra routers y aplica migraciones al arrancar
├── core/config.py           # configuración leída del .env (pydantic-settings)
├── db/                      # engine, sesión, Base de SQLAlchemy y runner de migraciones
├── models/                  # modelos ORM: Item, FileRecord, Ejecucion, PasoAgente y enums
├── schemas/                 # modelos Pydantic de entrada/salida
├── crud/                    # consultas a Postgres
├── agentes/                 # un archivo por agente (stubs) y contratos.py con la forma de cada salida
├── services/s3.py           # cliente y operaciones sobre S3
├── services/files.py        # operaciones que tocan S3 + BD a la vez
├── services/orquestador.py  # corre los 4 agentes en orden y persiste cada paso
└── api/routes/              # endpoints: health, items, files, consultas
migrations/                  # SQL versionado del esquema
tests/                       # tests con SQLite en memoria + moto (S3 simulado)
Dockerfile, docker-compose*.yml  # imagen de la API y modos de prueba local
```

## Puesta en marcha

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # y completa las credenciales (ver docs/SETUP_AWS.md)
fastapi dev app/main.py
```

Documentación interactiva: http://127.0.0.1:8000/docs

Para comprobar las conexiones:

- `GET /health/db`: ejecuta `SELECT 1` contra RDS.
- `GET /health/s3`: hace `head_bucket` sobre el bucket configurado.

## Probar en local con Docker

Requiere Docker Desktop encendido y el `.env` completo (las credenciales se pasan al contenedor; no se
copian a la imagen). Hay dos modos:

| Modo | Base de datos | S3 | Comando |
|------|---------------|----|---------|
| **Contra AWS** | RDS del `.env` | Bucket del `.env` | `docker compose up --build` |
| **Base local** | PostgreSQL 18 en Docker (vacía, se migra sola) | Bucket del `.env` | `docker compose -f docker-compose.yml -f docker-compose.local-db.yml up --build` |

La API queda en http://localhost:8000 (Swagger en `/docs`). Usa la **base local** para probar sin tocar los
datos del equipo ni depender de la conexión a RDS; los archivos sí se suben al bucket real.

```bash
docker compose up --build --watch     # reinicia la API cada vez que guardas un cambio en app/
docker compose logs -f api            # ver logs
docker compose down                   # detener (con base local: agrega los dos -f del comando de arriba)
docker compose -f docker-compose.yml -f docker-compose.local-db.yml down -v   # detener y borrar la base local
```

Con la base local, puedes conectarte desde DBeaver o psql a `localhost:5433` (base, usuario y contraseña:
`nttbanca`). La imagen solo contiene `app/`, `migrations/` y las dependencias (ver `.dockerignore`).

## Endpoints

### Items

| Método | Ruta                 | Descripción                                        |
|--------|----------------------|----------------------------------------------------|
| POST   | `/items`             | Crear                                              |
| GET    | `/items`             | Listar (`skip`, `limit`)                           |
| GET    | `/items/{id}`        | Obtener uno                                        |
| GET    | `/items/{id}/files`  | Archivos del item                                  |
| PATCH  | `/items/{id}`        | Actualizar campos parcialmente                     |
| DELETE | `/items/{id}`        | Eliminar el item, sus registros y sus objetos en S3 |

Campos normativos, todos opcionales al crear (los clientes que no los envían siguen funcionando igual):
`tipo` (`SBS` | `POLITICA_INTERNA`), `codigo_norma`, `fecha_vigencia` (`YYYY-MM-DD`), `estado`
(`VIGENTE` por defecto | `DEROGADA`) y `reemplaza_a` (id de otro documento; `null` lo quita).

### Files

| Método | Ruta                          | Descripción                                                  |
|--------|-------------------------------|--------------------------------------------------------------|
| POST   | `/files`                      | Subir (multipart: `file`, `item_id` opcional)                |
| GET    | `/files`                      | Listar registros (`item_id`, `skip`, `limit`)                |
| GET    | `/files/{id}`                 | Obtener el registro                                          |
| GET    | `/files/{id}/download`        | Descargar desde S3 (streaming, con el nombre original)       |
| GET    | `/files/{id}/presigned-url`   | URL temporal de descarga directa desde S3 (`expires_in`)     |
| PUT    | `/files/{id}`                 | Reemplazar el contenido (multipart: `file`)                  |
| PATCH  | `/files/{id}`                 | Cambiar `original_filename` o `item_id` (null = desvincular) |
| DELETE | `/files/{id}`                 | Eliminar registro y objeto en S3                             |

### Consultas (asistente normativo)

| Método | Ruta                               | Descripción                                                              |
|--------|------------------------------------|--------------------------------------------------------------------------|
| POST   | `/consultas`                       | Body `{"pregunta", "sesion_id"?}`. Responde **202** al instante con `{ejecucion_id, sesion_id, estado}` y corre el pipeline en segundo plano. Sin `sesion_id`, crea una sesión nueva. |
| GET    | `/consultas/{id}`                  | Ejecución con `estado`, `paso_actual`, `respuesta` y sus `pasos` en orden. Pensado para polling cada 1-2 s hasta `COMPLETADO` o `ERROR`. |
| GET    | `/sesiones/{sesion_id}/consultas`  | Historial de la sesión, más reciente primero (`limit`, por defecto 50).  |

Cómo avanza una ejecución: `PENDIENTE` → `EN_PROCESO` (con `paso_actual` = BUSCADOR, VIGENCIA, CONFLICTOS,
REDACTOR) → `COMPLETADO` (con `respuesta`; `paso_actual` vuelve a `null`). Si un agente falla, su paso queda en
`ERROR` con el mensaje, la ejecución pasa a `ERROR` con `paso_actual` en ese agente y el pipeline se detiene; la
API sigue funcionando.

**Agentes.** Cada uno vive en `app/agentes/<agente>.py` con la firma `(pregunta, contexto_previo) -> dict`, donde
`contexto_previo["BUSCADOR"]`, etc. trae la salida de los anteriores. Hoy son **stubs** con datos de ejemplo
(marcados `[Ejemplo]`). Para conectar el LLM, reemplaza el cuerpo de la función y respeta el contrato de
[`app/agentes/contratos.py`](app/agentes/contratos.py): el orquestador valida cada salida y, si no cumple, marca
el paso como `ERROR` indicando qué campo falla. `AGENT_STUB_DELAY_MS` (por defecto 1000) agrega una pausa en
cada stub para que en la demo se vea avanzar el pipeline. Ejemplos de cada agente con la API de Claude en
[docs/ASISTENTE_NORMATIVO.md § 5](docs/ASISTENTE_NORMATIVO.md#5-implementar-los-agentes-reales).

```bash
curl -X POST $API/consultas -H "Content-Type: application/json" \
  -d '{"pregunta": "¿Cuál es el plazo para reportar eventos de pérdida?"}'
curl $API/consultas/<ejecucion_id>
curl $API/sesiones/<sesion_id>/consultas
```

## Configurar AWS

La guía paso a paso para crear el bucket de S3, el usuario IAM y la base PostgreSQL en RDS, llenar el `.env` y
probar el backend está en **[docs/SETUP_AWS.md](docs/SETUP_AWS.md)**.

Para crear todo de una vez desde la terminal (en Windows, Git Bash), con el AWS CLI ya configurado:

```bash
bash scripts/aws_setup_dev.sh
```

## Desplegar en EC2

Para publicar la API en una EC2 junto a la RDS, de modo que otros puedan consumirla, sigue
**[docs/DEPLOY_EC2.md](docs/DEPLOY_EC2.md)**. En resumen:

```bash
bash scripts/aws_deploy_ec2.sh
```

Para publicar cambios del código, vuelve a correr el mismo comando.

## Tests

No necesitan credenciales: usan SQLite en memoria y S3 simulado con moto.

```powershell
pip install -r requirements-dev.txt
pytest
```

## Próximos pasos sugeridos

- Conectar los agentes al LLM (ver `app/agentes/`).
- Agregar autenticación a los endpoints.
- Si la API se reinicia a mitad de un pipeline, esa ejecución queda en `EN_PROCESO`; hoy no se retoma.
