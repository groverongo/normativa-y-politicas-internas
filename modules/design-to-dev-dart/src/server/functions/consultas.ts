import { createServerFn } from "@tanstack/react-start";
import type { ConsultAnswer } from "@/lib/domain/types";
import { askQuestion } from "@/server/nttdatabanca-client";
import { respuestaToConsultAnswer } from "@/server/nttdatabanca-adapter";

export const askQuestionFn = createServerFn({ method: "POST" })
  .validator((question: unknown): string => {
    if (typeof question !== "string" || question.trim().length === 0) {
      throw new Error("askQuestionFn requires a non-empty question");
    }
    return question;
  })
  .handler(async ({ data: question }): Promise<ConsultAnswer> => {
    const respuesta = await askQuestion(question);
    return respuestaToConsultAnswer({ id: crypto.randomUUID(), question, respuesta });
  });
