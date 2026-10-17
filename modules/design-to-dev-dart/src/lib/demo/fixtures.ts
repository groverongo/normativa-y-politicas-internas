/**
 * DATOS DE PRUEBA — ficticios, solo para demostración.
 * No representan documentos, versiones ni citas institucionales reales.
 * Reemplazar por servicios reales en src/services sin tocar la interfaz.
 */
import type { ConsultAnswer, NormativeDocument } from "@/lib/domain/types";

export const DEMO_REFERENCE_DATE = "2026-10-17";

export const demoDocuments: NormativeDocument[] = [
  {
    id: "d1", code: "POL-RC-002", title: "Política de Evaluación Crediticia", type: "Política",
    area: "Riesgo crediticio", owner: "Comité de Riesgos", isDemo: true,
    description: "Establece los criterios y parámetros para evaluar solicitudes de crédito, definir niveles de aprobación y documentar la decisión crediticia.",
    versions: [
      { v: "3.0", status: "approved", from: "2026-09-15", until: null, approved: "2026-09-12", by: "Comité de Riesgos", note: "Versión aprobada y aplicable." },
      { v: "2.0", status: "replaced", from: "2025-04-01", until: "2026-09-14", approved: "2025-03-27", by: "Comité de Riesgos", note: "Reemplazada por la versión 3.0." },
    ],
    relations: [{ kind: "replaces", target: "POL-RC-002 v2.0", status: "confirmada", note: "La versión 3.0 reemplaza la versión 2.0 desde el 15 sep 2026." }],
    classification: "Uso interno", uploaded: "2026-09-10", review: "2027-03-15",
  },
  {
    id: "d2", code: "CIR-RC-028", title: "Circular de Autoridades de Aprobación Crediticia", type: "Circular",
    area: "Riesgo crediticio", owner: "Lucía Paredes", isDemo: true, pendingValidation: true,
    description: "Circular con lineamientos de atribuciones y niveles de aprobación para operaciones crediticias. Existe una posible inconsistencia con la política vigente que requiere validación formal.",
    versions: [{ v: "1.0", status: "pending", from: null, until: null, approved: null, by: null, note: "Pendiente de validación; no asumir aplicabilidad hasta completar la revisión." }],
    relations: [{ kind: "potential_conflict", target: "POL-RC-002 v3.0", status: "no resuelta", note: "Posible contradicción en atribuciones de aprobación. No se ha determinado precedencia normativa." }],
    classification: "Uso interno", uploaded: "2026-10-16", review: "Pendiente de validación",
  },
  {
    id: "d3", code: "PR-OP-014", title: "Procedimiento de Gestión de Incidentes Operacionales", type: "Procedimiento",
    area: "Riesgo operacional", owner: "Jorge Salazar", isDemo: true,
    description: "Describe las etapas de registro, clasificación, escalamiento y cierre de incidentes operacionales, con responsables y tiempos de respuesta.",
    versions: [
      { v: "3.0", status: "approved", from: "2026-12-01", until: null, approved: "2026-10-16", by: "Responsable de Riesgo Operacional", note: "Aprobada, pero su fecha de entrada en vigor es futura." },
      { v: "2.0", status: "approved", from: "2025-06-01", until: "2026-11-30", approved: "2025-05-28", by: "Responsable de Riesgo Operacional", note: "Continúa aplicable hasta la entrada en vigor de la versión 3.0." },
    ],
    relations: [{ kind: "replaces", target: "PR-OP-014 v2.0", status: "programada", note: "La versión 3.0 reemplazará a la 2.0 desde el 01 dic 2026." }],
    classification: "Uso interno", uploaded: "2026-10-16", review: "2027-06-01",
  },
  {
    id: "d4", code: "MAN-CN-004", title: "Manual de Cumplimiento Normativo", type: "Manual",
    area: "Cumplimiento", owner: "Equipo de Cumplimiento", isDemo: true,
    description: "Reúne el marco operativo para el seguimiento de obligaciones, controles internos, escalamiento de incidencias y evidencia de cumplimiento.",
    versions: [
      { v: "2.1", status: "approved", from: "2026-02-01", until: null, approved: "2026-01-27", by: "Oficial de Cumplimiento", note: "Versión aplicable; revisión periódica programada." },
      { v: "2.0", status: "replaced", from: "2025-01-01", until: "2026-01-31", approved: "2024-12-18", by: "Oficial de Cumplimiento", note: "Reemplazada por la versión 2.1." },
    ],
    relations: [], classification: "Confidencial interno", uploaded: "2026-01-25", review: "2026-11-30",
  },
  {
    id: "d5", code: "POL-RC-009", title: "Política de Excepciones Crediticias", type: "Política",
    area: "Riesgo crediticio", owner: "Por asignar", isDemo: true,
    description: "Define condiciones y controles para solicitar, evaluar y documentar excepciones a los parámetros ordinarios de crédito. La información de vigencia requiere confirmación del responsable documental.",
    versions: [{ v: "1.2", status: "approved", from: null, until: null, approved: "2025-08-10", by: "Comité de Riesgos", note: "Aprobación registrada, pero faltan metadatos de vigencia verificables." }],
    relations: [{ kind: "related", target: "POL-RC-002 v3.0", status: "por verificar", note: "Relación temática identificada; alcance y excepciones deben validarse." }],
    classification: "Uso interno", uploaded: "2025-08-08", review: "Fecha por confirmar",
  },
  {
    id: "d6", code: "INS-AI-006", title: "Instructivo de Evidencia de Auditoría", type: "Procedimiento",
    area: "Auditoría interna", owner: "Carlos Mendoza", isDemo: true,
    description: "Establece requisitos mínimos para registrar, custodiar y referenciar evidencia durante revisiones de auditoría interna.",
    versions: [{ v: "1.4", status: "approved", from: "2026-05-01", until: null, approved: "2026-04-25", by: "Jefatura de Auditoría", note: "Versión aprobada y aplicable." }],
    relations: [], classification: "Confidencial interno", uploaded: "2026-04-23", review: "2027-05-01",
  },
];

type DemoAnswer = Omit<ConsultAnswer, "id" | "question" | "answeredAt" | "source"> & { match: string[] };

export const demoAnswers: DemoAnswer[] = [
  {
    match: ["vigente", "versión", "version", "evaluación", "crediticia"],
    title: "La versión aplicable es POL-RC-002 v3.0",
    level: "suficiente",
    facts: [
      "A la fecha de referencia (17 oct 2026), la versión 3.0 de la Política de Evaluación Crediticia figura aprobada y aplicable desde el 15 sep 2026.",
      "La versión 2.0 fue reemplazada y no debe usarse como referencia vigente.",
    ],
    interpretation: null,
    evidence: [
      { code: "POL-RC-002", title: "Política de Evaluación Crediticia", version: "v3.0", section: "6. Vigencia y control de versiones", page: "12", quote: "La presente política entra en vigor a partir del [[15 de septiembre de 2026]] y deja sin efecto la versión 2.0 desde esa fecha.", why: "Sustenta la fecha de vigencia y el reemplazo de la versión anterior." },
      { code: "POL-RC-002", title: "Política de Evaluación Crediticia", version: "v2.0", section: "Historial de cambios", page: "11", quote: "Versión 2.0: [[reemplazada por la versión 3.0]] con fecha de aplicación 15/09/2026.", why: "Confirma que la versión anterior ya no es la referencia aplicable." },
    ],
    warnings: [],
  },
  {
    match: ["límite", "limite", "aprobación", "aprobacion", "empresariales", "atribución"],
    title: "Los límites dependen del nivel de atribución",
    level: "parcial",
    facts: ["La política vigente exige que las aprobaciones respeten el nivel de atribución correspondiente."],
    interpretation:
      "Existe una circular pendiente de validación que podría entrar en conflicto con la política. No es seguro concluir un monto específico hasta resolver esa revisión.",
    evidence: [
      { code: "POL-RC-002", title: "Política de Evaluación Crediticia", version: "v3.0", section: "4. Niveles de atribución", page: "8", quote: "Las operaciones deberán ser aprobadas conforme a los [[niveles de atribución vigentes]] y a los límites establecidos para cada instancia.", why: "Establece el principio general de aprobación." },
      { code: "CIR-RC-028", title: "Circular de Autoridades de Aprobación Crediticia", version: "v1.0", section: "3. Facultades especiales", page: "4", quote: "Se propone actualizar los límites de aprobación para determinadas operaciones empresariales. [[Documento pendiente de validación]].", why: "La circular aún no está validada; no debe tratarse como regla vigente." },
    ],
    warnings: ["Conflicto potencial: CIR-RC-028 requiere validación humana. No aplicar sus límites propuestos como norma vigente."],
  },
  {
    match: ["contradice", "contradicción", "conflicto", "circular"],
    title: "No resuelvas la contradicción por suposición",
    level: "revision",
    facts: [
      "CIR-RC-028 está registrada como pendiente de validación.",
      "POL-RC-002 v3.0 es la versión aprobada y vigente de la política.",
    ],
    interpretation:
      "Antes de decidir qué regla prevalece, debe comprobarse el estado de aprobación, la vigencia, la jerarquía normativa y la relación formal entre ambos documentos. La fecha más reciente no basta para determinar precedencia.",
    evidence: [
      { code: "POL-RC-002", title: "Política de Evaluación Crediticia", version: "v3.0", section: "6. Vigencia y control de versiones", page: "12", quote: "La política vigente es la versión aprobada con fecha de aplicación 15/09/2026, salvo modificación formal posterior.", why: "Referencia aprobada para contrastar el documento cuestionado." },
      { code: "CIR-RC-028", title: "Circular de Autoridades de Aprobación Crediticia", version: "v1.0", section: "Estado del documento", page: "1", quote: "Estado registrado: [[pendiente de validación]]. La aplicabilidad queda sujeta a confirmación del responsable normativo.", why: "No hay base suficiente para tratar esta circular como disposición vigente." },
    ],
    warnings: ["Acción recomendada: derivar CIR-RC-028 al responsable de cumplimiento y registrar la decisión con su justificación."],
  },
];

export const insufficientAnswer: DemoAnswer = {
  match: [],
  title: "No hay evidencia suficiente para responder con seguridad",
  level: "insuficiente",
  facts: [],
  interpretation: null,
  evidence: [],
  warnings: [
    "No se encontraron fragmentos que respondan de forma directa. La plataforma se abstiene de emitir una conclusión normativa. Prueba con una consulta sobre vigencia, límites de aprobación o conflictos entre documentos.",
  ],
};

export const demoSuggestions = [
  { label: "¿Qué versión está vigente?", prompt: "¿Qué versión de la política de evaluación crediticia está vigente?" },
  { label: "Límites de aprobación", prompt: "¿Cuáles son los límites de aprobación para operaciones empresariales?" },
  { label: "¿La circular contradice la política?", prompt: "¿La circular CIR-RC-028 contradice la política vigente?" },
];
