import { createFileRoute } from "@tanstack/react-router";
import { LibraryPage } from "@/components/hz/LibraryPage";

type Search = { q?: string | undefined };

export const Route = createFileRoute("/biblioteca/")({
  validateSearch: (s: Record<string, unknown>): Search => ({
    q: typeof s["q"] === "string" && s["q"] ? s["q"] : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Biblioteca documental · Horizonte Intelligence" },
      { name: "description", content: "Explora documentos normativos, versiones y estado de vigencia." },
      { property: "og:title", content: "Biblioteca documental · Horizonte Intelligence" },
      { property: "og:description", content: "Repositorio central de políticas, circulares, manuales y procedimientos." },
    ],
  }),
  component: LibraryPage,
});

