import { describe, expect, it } from "vitest";
import { assessValidity } from "./validity";
import { demoDocuments } from "@/lib/demo/fixtures";

const doc = (c: string) => demoDocuments.find((d) => d.code === c)!;
const DATE = "2026-10-17";

describe("assessValidity", () => {
  it("picks v3.0 of POL-RC-002, not replaced v2.0", () => {
    const a = assessValidity(doc("POL-RC-002"), DATE);
    expect(a.state).toBe("Vigente");
    expect(a.version?.v).toBe("3.0");
  });
  it("keeps v2.0 of PR-OP-014 applicable while v3.0 is future", () => {
    const a = assessValidity(doc("PR-OP-014"), DATE);
    expect(a.version?.v).toBe("2.0");
    expect(a.futureVersion?.v).toBe("3.0");
  });
  it("never concludes vigencia for a pending document", () => {
    const a = assessValidity(doc("CIR-RC-028"), DATE);
    expect(a.state).toBe("Pendiente");
    expect(a.version).toBeNull();
  });
  it("flags approved version without dates as uncertain", () => {
    const a = assessValidity(doc("POL-RC-009"), DATE);
    expect(a.state).toBe("Revisión");
    expect(a.uncertain).toBe(true);
  });
});
