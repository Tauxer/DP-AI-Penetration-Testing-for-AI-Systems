# Dashboard de seguridad · Red Turing + DeepTeam

Una sola interfaz (React + Vite) con barra lateral para los dos motores de
red teaming del proyecto TramiBot, servida por un backend FastAPI que reutiliza
el código de Red Turing y envuelve DeepTeam.

```
dashboard-seguridad/
├── backend/
│   ├── app.py               FastAPI: /api/redturing/* y /api/deepteam/*; sirve frontend/dist
│   ├── deepteam_runner.py   catálogo, modelos adversario/juez, ejecución en hilo, JSON de resultados
│   ├── objetivos.py         registro compartido de agentes (lee/escribe Red-Turing/targets.yaml)
│   └── config.json          valores por defecto (se crea al guardar desde la UI)
├── frontend/                React 19 + Vite + TypeScript, sin librerías de UI
│   └── src/pages/           Guia · Objetivos · RedTuring{Lista,Detalle,Nueva,Live} · DeepTeam{Lista,Detalle,Nueva,Estado}
└── run.sh
```

## Arrancar

```bash
./run.sh          # http://127.0.0.1:8740
./run.sh dev      # desarrollo con recarga: Vite en 5173 con proxy a 8740
```

Usa el intérprete conda `DP-LangChain-Seguridad` porque DeepTeam exige Python
< 3.14 y el callback importa el agente real (LangChain). No hace falta tener
abierto el dashboard antiguo de Red Turing: este lee la misma carpeta
`Red-Turing/reports/` y usa el mismo lanzador.

## Para quién es

Para el equipo de AI Engineer. La idea: cualquier persona del equipo registra su
agente (normalmente por su URL), lanza Red Turing para la regresión semanal y
DeepTeam para explorar vectores nuevos, y lee los resultados en el mismo sitio.
La página **Guía** del propio dashboard explica el flujo paso a paso.

## Objetivos: el agente que se prueba

Sección **Objetivos**, compartida por los dos motores. Se guarda en
`Red-Turing/targets.yaml`, así que también sirve para el CLI de Red Turing.

| Tipo | Qué necesitas | Sirve para |
|---|---|---|
| **Endpoint HTTP** | URL, método, cuerpo JSON con `{payload}` (y `{session_id}`), ruta de la respuesta, códigos de bloqueo, nombre de la variable de entorno del token | Red Turing y DeepTeam. El caso normal en el equipo. |
| **Agente Python** | ruta del proyecto, módulo y función texto→texto; opcionalmente su guardrail | Ambos; además permite medir el guardrail y el LLM por separado |
| **Solo guardrail** | ruta, módulo y función `(es_seguro, motivo)` | Solo Red Turing, gratis |
| **Simulado** | modo | Verificar el arnés |

"Probar conexión" envía un saludo y muestra respuesta y latencia. Los tokens
nunca se guardan: se anota el nombre de la variable de entorno y el valor lo
pone quien arranca el backend (`export RT_TOKEN_MI_AGENTE=...`).

## Qué hay en cada sección

**Red Turing** (rojo): corridas del corpus fijo (87 casos YAML), detalle con
ASR, ASR solo LLM, columnas Guardrail / LLM solo / Respuesta del agente,
comparación con otra corrida, formulario para lanzar con confirmación de coste
y vista en vivo por SSE.

**DeepTeam** (morado): evaluaciones generadas por un LLM adversario y juzgadas
por otro. En "Nueva evaluación" eliges:

- **Modelo adversario** (DeepTeam lo llama *simulator*): inventa y disfraza los
  ataques. gpt-4o-mini basta.
- **Modelo juez**: decide 0/1 con una razón. Recomendado gpt-4.1; gpt-4o-mini
  confunde rechazos con fugas.
- Vulnerabilidades (37, con sus tipos), métodos de ataque (22 de un turno y 5
  multi-turno), ataques por tipo, sistema completo o solo LLM, propósito.
- "Ataques en español": envuelve cada método con `EnEspanol` porque DeepTeam
  reescribe en inglés al mejorar los payloads.

Los resultados se guardan en `deepteam-pruebas/resultados/dt-*.json` y se
muestran con tasa de fallo, desglose por vulnerabilidad y por método, y cada
caso con payload, respuesta de TramiBot y razón del juez.

## Reglas

- Solo localhost; Host y Origin se verifican. Los informes contienen los
  payloads que atravesaron tus defensas y las respuestas del agente.
- Una sola actividad a la vez entre los dos motores: comparten el agente.
- Todo lo que cuesta dinero pide confirmación explícita con la cifra de llamadas.
