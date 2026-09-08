# DP · AI Penetration Testing for AI Systems

Framework de red teaming para agentes LLM, construido en el Programa AI Engineer
de DataPath. Dos motores complementarios y un dashboard que los une.

Todo vive bajo `Sistema-de-Testing-de-Seguridad/`:

| Carpeta | Qué es |
|---|---|
| `Red-Turing/` | Arnés de ataques con **corpus fijo** (87 casos YAML) y veredictos determinísticos: canario, marcador, capa del guardrail que bloqueó. Para regresión. Tiene CLI y su propio dashboard mínimo. |
| `dashboard-seguridad/` | **Dashboard React + Vite** con backend FastAPI. Barra lateral con Red Turing y DeepTeam, registro de objetivos (agentes por endpoint HTTP o por código), elección de modelo adversario y juez, guía para el equipo. |
| `deepteam-pruebas/` | Envoltorio `EnEspanol` que el dashboard usa para que DeepTeam ataque en español, scripts de exploración y carpeta de resultados. |

DeepTeam (Confident AI, Apache 2.0) se instala con pip; no se versiona aquí.

## Cómo funciona, en una frase

**DeepTeam descubre, Red Turing fija.** Un LLM adversario inventa ataques
contra tu agente y otro LLM juzga si cedió (exploración, no repetible); los
ataques que funcionan se copian al corpus de Red Turing como casos YAML y desde
entonces se miden igual en cada corrida (regresión, determinística).

## Puesta en marcha

Requisitos: Python 3.10 a 3.13, Node 20 o superior, una clave de OpenAI.

```bash
git clone https://github.com/KevinInoCol/DP-AI-Penetration-Testing-for-AI-Systems.git
cd DP-AI-Penetration-Testing-for-AI-Systems/Sistema-de-Testing-de-Seguridad

# 1. Entorno Python
python -m venv .venv && source .venv/bin/activate        # o tu entorno conda
pip install -r dashboard-seguridad/backend/requirements.txt

# 2. Credenciales (nunca se versionan)
cp dashboard-seguridad/backend/.env.example dashboard-seguridad/backend/.env
#    → rellena OPENAI_API_KEY (adversario y juez de DeepTeam, juez opcional de Red Turing)

# 3. Objetivos: qué agentes se van a probar
cp Red-Turing/targets.example.yaml Red-Turing/targets.yaml
#    → o regístralos desde el dashboard, sección Objetivos

# 4. Arrancar
cd dashboard-seguridad && ./run.sh                        # http://127.0.0.1:8740
```

La primera vez compila el frontend (`npm install` + `npm run build`). Lee la
página **Guía de uso** del dashboard: explica cuándo usar cada motor, cómo
registrar un agente por su URL y cómo leer los resultados.

## Probar un agente desplegado (el caso normal)

En **Objetivos → Registrar objetivo → Endpoint HTTP** indica la URL, el cuerpo
JSON con `{payload}` (el mensaje) y `{session_id}` (la conversación), la ruta
de la respuesta y, si hay token, el **nombre** de la variable de entorno que lo
contiene. "Probar conexión" comprueba que responde. Desde ahí, el mismo
objetivo aparece en **Red Turing → Nueva corrida** y en **DeepTeam → Nueva
evaluación**.

Para medir el guardrail y el modelo por separado hace falta un objetivo de tipo
*Agente Python* (importable desde el servidor, con su guardrail declarado).

## Seguridad del propio framework

- El dashboard solo escucha en `127.0.0.1` y rechaza peticiones cuyo Host u
  Origin no sean locales. Los informes contienen los payloads que atravesaron
  las defensas y las respuestas literales del agente: no lo expongas.
- Los informes (`Sistema-de-Testing-de-Seguridad/Red-Turing/reports/*.json`,
  `Sistema-de-Testing-de-Seguridad/deepteam-pruebas/resultados/*.json`)
  y `targets.yaml` están fuera del repositorio a propósito.
- Todo lo que cuesta dinero pide confirmación con la cifra de llamadas.
- Solo contra sistemas propios o con autorización escrita.

## Documentación

- `Sistema-de-Testing-de-Seguridad/Red-Turing/README.md` — el arnés, el corpus, los detectores, el ASR.
- `Sistema-de-Testing-de-Seguridad/dashboard-seguridad/README.md` — arquitectura del dashboard y su API.
- `Sistema-de-Testing-de-Seguridad/deepteam-pruebas/README.md` — lo aprendido probando DeepTeam.

Autor: Ing. Kevin Inofuente Colque — DataPath, Programa AI Engineer.
