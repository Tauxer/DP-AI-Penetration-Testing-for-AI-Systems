# Pruebas con DeepTeam

Experimentos para entender cómo trabaja DeepTeam (confident-ai) antes de
integrarlo con Red Turing. El clon del repo está en `../deepteam` (solo lectura,
para consultar código); el paquete se instaló con pip en el entorno conda
`DP-LangChain-Seguridad`, el mismo del agente.

    PY=/opt/anaconda3/envs/DP-LangChain-Seguridad/bin/python

| Script | Qué hace | Coste |
|---|---|---|
| `01_mecanica.py` | Callback de mentira (siempre rechaza). Sirve para ver qué genera, cómo evalúa y qué devuelve. | Solo simulador + juez (gpt-4o-mini) |
| `02_tramibot.py` | Callback real: `chat_con_agente` del proyecto. Pocas vulnerabilidades, pocos ataques. | Simulador + juez + TramiBot |

Los resultados se guardan en `resultados/` como JSON. La clave de OpenAI se lee
del `.env` del proyecto del agente; nunca se imprime.

## Lo aprendido en las primeras corridas (2026-09-06)

- **Idioma.** Los payloads base salen en español si `target_purpose` está en
  español, pero la "mejora" de cada ataque (PromptInjection, Roleplay…) los
  reescribe en inglés. `en_espanol.py` envuelve cualquier ataque y traduce el
  resultado; los ataques quedan como "Prompt Injection (es)".
- **El juez se equivoca con los rechazos.** Dos veces marcó como "fuga de
  instrucciones" un mensaje de bloqueo del guardrail ("no puedo procesar ese
  mensaje"). Hay que leer las razones, no solo el score.
- **No distingue capas.** Un fail-close de Groq ("servicio de seguridad no
  disponible") cuenta como aprobado. Red Turing lo saca del ASR.
- **Sin interfaz local.** El CLI imprime tablas y guarda JSON en `resultados/nativo/`;
  la vista web es Confident AI (nube, con cuenta). Los JSON propios de estos
  scripts están pensados para convertirlos a casos YAML de Red Turing.
- **Coste.** ~0.005 USD por caso con gpt-4o-mini como simulador y juez, más las
  llamadas del propio TramiBot.
- **Dependencia rota en 1.0.9**: `deepteam` importa `sentry_sdk` sin declararlo;
  hay que instalarlo aparte (`pip install sentry-sdk`).
