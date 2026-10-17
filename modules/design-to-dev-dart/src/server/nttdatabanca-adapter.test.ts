import { describe, expect, it } from "vitest";
import { respuestaToConsultAnswer } from "./nttdatabanca-adapter";
import type { NttdatabancaRespuestaDTO } from "@/lib/domain/nttdatabanca-types";

// Mirrors modules/nttdatabanca/ejemplo_respuesta.json verbatim.
const exampleResponse: NttdatabancaRespuestaDTO = {
  respuesta: "Deben probarse como mínimo dos veces al año [int-pol-continuidad-v2#articulo-3].",
  sin_respuesta: false,
  citas: [
    {
      chunk_id: "int-pol-continuidad-v2#articulo-3",
      cita_textual: "deberán probarse como mínimo dos veces al año",
      documento: "Política interna de Continuidad del Negocio (Banco Demo) (POL-CN-01 v2)",
      ruta: "Artículo 3",
      pagina: 1,
      estado: "vigente",
    },
  ],
  citas_descartadas: 1,
  contradicciones: [
    {
      chunk_a: "int-proc-pruebas-bcp#articulo-2",
      chunk_b: "int-pol-continuidad-v2#articulo-3",
      explicacion: "Una vez al año vs. dos veces al año.",
      prevalece: "int-pol-continuidad-v2",
      criterio: "mayor jerarquía normativa",
    },
  ],
  alertas: [
    {
      tipo: "derogado",
      doc_id: "int-pol-continuidad-v1",
      detalle:
        "Política interna de Continuidad del Negocio (Banco Demo) (POL-CN-01 v1) fue derogado / dejado sin efecto por Política interna de Continuidad del Negocio (Banco Demo) (POL-CN-01 v2). No usar como norma vigente.",
    },
  ],
  fuentes: [],
};

const emptyResponse = (
  overrides: Partial<NttdatabancaRespuestaDTO> = {},
): NttdatabancaRespuestaDTO => ({
  respuesta: "",
  sin_respuesta: true,
  citas: [],
  citas_descartadas: 0,
  contradicciones: [],
  alertas: [],
  fuentes: [],
  ...overrides,
});

describe("respuestaToConsultAnswer", () => {
  it("maps the real example response end to end", () => {
    const answer = respuestaToConsultAnswer({
      id: "1",
      question: "¿cada cuánto?",
      respuesta: exampleResponse,
    });
    expect(answer.source).toBe("backend");
    expect(answer.level).toBe("revision"); // has a contradiccion
    expect(answer.title).toBe("Respuesta con una contradicción normativa detectada");
    expect(answer.facts).toEqual(["Deben probarse como mínimo dos veces al año."]);
    expect(answer.interpretation).toBeNull();
  });

  it("strips inline [chunk_id] citation markers from the displayed text", () => {
    const answer = respuestaToConsultAnswer({ id: "1", question: "q", respuesta: exampleResponse });
    expect(answer.facts[0]).not.toContain("[");
  });

  it("maps a cita to an evidence fragment with doc_id derived from chunk_id", () => {
    const answer = respuestaToConsultAnswer({ id: "1", question: "q", respuesta: exampleResponse });
    expect(answer.evidence).toEqual([
      {
        code: "int-pol-continuidad-v2",
        title: "Política interna de Continuidad del Negocio (Banco Demo) (POL-CN-01 v2)",
        version: "v2",
        section: "Artículo 3",
        page: "1",
        quote: "deberán probarse como mínimo dos veces al año",
        why: "Cita validada contra el fragmento recuperado.",
      },
    ]);
  });

  it("includes alertas, contradicciones and citas_descartadas as warnings", () => {
    const answer = respuestaToConsultAnswer({ id: "1", question: "q", respuesta: exampleResponse });
    expect(answer.warnings).toHaveLength(3);
    expect(answer.warnings[0]).toContain("derogado");
    expect(answer.warnings[1]).toContain("Contradicción entre");
    expect(answer.warnings[2]).toContain("Se descartaron 1 cita");
  });

  it("marks sin_respuesta as insuficiente with no evidence", () => {
    const answer = respuestaToConsultAnswer({
      id: "1",
      question: "¿capital de Francia?",
      respuesta: emptyResponse(),
    });
    expect(answer.level).toBe("insuficiente");
    expect(answer.title).toBe("Sin evidencia suficiente en la biblioteca documental");
    expect(answer.evidence).toEqual([]);
    expect(answer.facts).toEqual([]);
  });

  it("treats zero validated citas as insuficiente even when sin_respuesta is false", () => {
    const answer = respuestaToConsultAnswer({
      id: "1",
      question: "q",
      respuesta: emptyResponse({ sin_respuesta: false, respuesta: "algo" }),
    });
    expect(answer.level).toBe("insuficiente");
  });

  it("marks parcial when there are alertas but no contradicciones", () => {
    const resp = emptyResponse({
      sin_respuesta: false,
      respuesta: "ok",
      citas: [
        {
          chunk_id: "doc-1#a1",
          cita_textual: "texto",
          documento: "Documento (v1)",
          ruta: "Art 1",
          pagina: 1,
          estado: "vigente",
        },
      ],
      alertas: [{ tipo: "derogado", doc_id: "doc-0", detalle: "detalle" }],
    });
    const answer = respuestaToConsultAnswer({ id: "1", question: "q", respuesta: resp });
    expect(answer.level).toBe("parcial");
  });

  it("marks suficiente when there are citas and no alertas/contradicciones", () => {
    const resp = emptyResponse({
      sin_respuesta: false,
      respuesta: "ok",
      citas: [
        {
          chunk_id: "doc-1#a1",
          cita_textual: "texto",
          documento: "Documento (v1)",
          ruta: "Art 1",
          pagina: 1,
          estado: "vigente",
        },
      ],
    });
    const answer = respuestaToConsultAnswer({ id: "1", question: "q", respuesta: resp });
    expect(answer.level).toBe("suficiente");
  });
});
