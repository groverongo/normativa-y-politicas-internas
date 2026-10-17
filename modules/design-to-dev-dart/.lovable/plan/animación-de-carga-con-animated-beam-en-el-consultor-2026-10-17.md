# Animación de carga con Animated Beam en el Consultor

## Opinión
Buena idea, siempre que la animación muestre el recorrido real de la consulta y no sirva solo de adorno. Animated Beam une nodos con haces de luz en movimiento, así que encaja bien con el flujo que ya promete el consultor:

```text
Consulta  ──►  Biblioteca documental  ──►  Evaluación de vigencia  ──►  Respuesta con evidencia
```

Dos cuidados:
- **Honestidad:** en modo demo hay que mantener la etiqueta "Simulado", para que la animación no dé a entender que hay procesamiento real.
- **Sobriedad:** los haces van en negro o grafito sobre el fondo cálido, sin degradados de colores, para respetar la identidad del prototipo.

## Qué se verá
- Al enviar una pregunta, la tarjeta de bienvenida se reemplaza por un panel con 4 nodos circulares (icono + etiqueta) unidos por haces animados.
- La etapa activa se resalta en negro y debajo aparece un texto de estado, por ejemplo "Buscando fragmentos en 6 documentos…".
- En modo demo las etapas avanzan con tiempos simulados. Cuando haya un servidor real, avanzarán según el estado que este informe.
- En pantallas de tableta los nodos siguen en una sola fila, más compactos. En móvil se ponen en vertical.
- Si el usuario tiene activada la opción "reducir movimiento", los haces quedan estáticos.
- El buscador de la barra superior lleva a la Biblioteca, donde la búsqueda es instantánea, así que ahí no se usa esta animación. Solo aparece en el Consultor.

## Detalles técnicos
- Instalar el componente: `npx shadcn@latest add @magicui/animated-beam` (crea `src/components/ui/animated-beam.tsx` y depende de `motion`).
- Ajustar los colores del componente a tokens semánticos (`--primary`, `--border`) en lugar de los degradados por defecto.
- Nuevo componente `src/components/hz/ConsultProgress.tsx` con los 4 nodos y sus refs, que recibe `stage: "consulta" | "recuperacion" | "vigencia" | "respuesta"`.
- Extender `HorizonteServices.askQuestion` con un callback opcional `onStage(stage)`. El proveedor demo lo emite con retrasos simulados y el futuro backend lo emitirá con el progreso real. La interfaz sigue hablando solo con `services`.
- Reemplazar el bloque de carga actual (spinner) en `src/routes/index.tsx` por `<ConsultProgress />`.
- Respetar `prefers-reduced-motion`.
