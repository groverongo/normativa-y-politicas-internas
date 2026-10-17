/**
 * Service layer. UI only talks to `services`. Today it is wired to the demo
 * provider; swap `demoProvider` for a backend provider (server functions)
 * implementing the same interface without touching components.
 */
import type {
  ConsultAnswer,
  NormativeDocument,
  ValidationFinding,
} from "@/lib/domain/types";
import { runLocalChecks } from "@/lib/domain/validity";
import {
  DEMO_REFERENCE_DATE,
  demoAnswers,
  demoDocuments,
  insufficientAnswer,
} from "@/lib/demo/fixtures";

export interface ProcessingStatus {
  documentCode: string;
  stage: "no_disponible" | "en_cola" | "procesando" | "indexado" | "error";
  detail: string;
}

export type ConsultStage = "consulta" | "recuperacion" | "vigencia" | "respuesta";

export interface HorizonteServices {
  mode: "demo" | "backend";
  referenceDate: () => string;
  listDocuments: () => Promise<NormativeDocument[]>;
  getDocument: (code: string) => Promise<NormativeDocument | null>;
  askQuestion: (question: string, onStage?: (stage: ConsultStage) => void) => Promise<ConsultAnswer>;
  runValidations: () => Promise<ValidationFinding[]>;
  getProcessingStatus: (code: string) => Promise<ProcessingStatus>;
  uploadDocument: (file: File) => Promise<never>;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class NotImplementedError extends Error {}

const demoProvider: HorizonteServices = {
  mode: "demo",
  referenceDate: () => DEMO_REFERENCE_DATE,
  async listDocuments() {
    await delay(150);
    return demoDocuments;
  },
  async getDocument(code) {
    await delay(100);
    return demoDocuments.find((d) => d.code === code) ?? null;
  },
  async askQuestion(question, onStage) {
    // Simulated timings: the demo has no real pipeline behind these stages.
    for (const [stage, ms] of [["consulta", 500], ["recuperacion", 1100], ["vigencia", 900], ["respuesta", 600]] as const) {
      onStage?.(stage);
      await delay(ms);
    }
    const q = question.toLowerCase();
    const hit = demoAnswers.find((a) => a.match.some((k) => q.includes(k))) ?? insufficientAnswer;
    const { match: _m, ...rest } = hit;
    return {
      ...rest,
      id: crypto.randomUUID(),
      question,
      answeredAt: new Date().toISOString(),
      source: "demo",
    };
  },
  async runValidations() {
    await delay(300);
    return runLocalChecks(demoDocuments, DEMO_REFERENCE_DATE);
  },
  async getProcessingStatus(code) {
    return {
      documentCode: code,
      stage: "no_disponible",
      detail: "El procesamiento documental aún no está conectado.",
    };
  },
  async uploadDocument() {
    throw new NotImplementedError(
      "La carga de documentos estará disponible cuando se conecte el almacenamiento y el procesamiento documental.",
    );
  },
};

export const services: HorizonteServices = demoProvider;
