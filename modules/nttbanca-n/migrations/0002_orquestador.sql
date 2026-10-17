-- Asistente normativo SBS: metadatos normativos en los documentos (items) y estado del orquestador.

-- 1. Documentos: tipo, código, vigencia y cadena de reemplazos.
--    Todas las columnas son opcionales o tienen default: los registros y clientes actuales siguen funcionando.
ALTER TABLE items ADD COLUMN IF NOT EXISTS tipo VARCHAR(20);
ALTER TABLE items ADD COLUMN IF NOT EXISTS codigo_norma TEXT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS fecha_vigencia DATE;
ALTER TABLE items ADD COLUMN IF NOT EXISTS estado VARCHAR(20) NOT NULL DEFAULT 'VIGENTE';
ALTER TABLE items ADD COLUMN IF NOT EXISTS reemplaza_a INTEGER REFERENCES items (id) ON DELETE SET NULL;

ALTER TABLE items ADD CONSTRAINT ck_items_tipo CHECK (tipo IN ('SBS', 'POLITICA_INTERNA'));
ALTER TABLE items ADD CONSTRAINT ck_items_estado CHECK (estado IN ('VIGENTE', 'DEROGADA'));
ALTER TABLE items ADD CONSTRAINT ck_items_reemplaza_a_distinto CHECK (reemplaza_a <> id);

CREATE INDEX IF NOT EXISTS ix_items_codigo_norma ON items (codigo_norma);
CREATE INDEX IF NOT EXISTS ix_items_reemplaza_a ON items (reemplaza_a);

-- 2. Ejecución: una pregunta del analista y el avance del pipeline.
CREATE TABLE IF NOT EXISTS ejecucion (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sesion_id      UUID NOT NULL,
    pregunta       TEXT NOT NULL,
    estado         VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
                   CONSTRAINT ck_ejecucion_estado
                   CHECK (estado IN ('PENDIENTE', 'EN_PROCESO', 'COMPLETADO', 'ERROR')),
    paso_actual    VARCHAR(20)
                   CONSTRAINT ck_ejecucion_paso_actual
                   CHECK (paso_actual IN ('BUSCADOR', 'VIGENCIA', 'CONFLICTOS', 'REDACTOR')),
    respuesta      TEXT,
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Historial de una sesión, más reciente primero
CREATE INDEX IF NOT EXISTS ix_ejecucion_sesion_id_creado_en ON ejecucion (sesion_id, creado_en);

-- 3. Paso de agente: la salida de cada agente dentro de una ejecución.
CREATE TABLE IF NOT EXISTS paso_agente (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ejecucion_id UUID NOT NULL REFERENCES ejecucion (id) ON DELETE CASCADE,
    agente       VARCHAR(20) NOT NULL
                 CONSTRAINT ck_paso_agente_agente
                 CHECK (agente IN ('BUSCADOR', 'VIGENCIA', 'CONFLICTOS', 'REDACTOR')),
    orden        INTEGER NOT NULL,
    estado       VARCHAR(20) NOT NULL
                 CONSTRAINT ck_paso_agente_estado CHECK (estado IN ('COMPLETADO', 'ERROR')),
    salida       JSONB,
    duracion_ms  INTEGER NOT NULL,
    error        TEXT,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_paso_agente_ejecucion_orden UNIQUE (ejecucion_id, orden)
);
