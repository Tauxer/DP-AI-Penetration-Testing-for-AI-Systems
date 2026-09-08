"""
Dashboard local de Red Turing: lee los JSON de `reports/`, los sirve en el
navegador y permite lanzar corridas nuevas con progreso en vivo.

No requiere nada que no venga con Python. Un servidor `http.server` expone una
API JSON, un flujo de eventos (SSE) para el progreso y una página estática que
hace todo el trabajo en el cliente.

Lanzar desde el navegador no relaja las garantías del CLI, las traslada:

- una sola corrida a la vez;
- los objetivos que cuestan dinero (`agente`, `http`) exigen una confirmación
  explícita que muestra cuántas llamadas reales va a hacer;
- cancelación cooperativa: lo que ya salió termina, lo demás no se envía;
- solo escucha en 127.0.0.1 y rechaza cualquier petición cuyo Host u Origin no
  sean locales, para que otra web abierta en el mismo navegador no pueda
  disparar un ataque contra tu agente.

Ejecutar:
    python -m redturing dashboard
"""

from .lanzador import CorridaEnCurso, Lanzador, RequiereConfirmacion, planificar
from .server import (
    DIRECTORIO_INFORMES,
    comparar_archivos,
    listar_corridas,
    origen_permitido,
    servir,
)

__all__ = [
    "CorridaEnCurso",
    "DIRECTORIO_INFORMES",
    "Lanzador",
    "RequiereConfirmacion",
    "comparar_archivos",
    "listar_corridas",
    "origen_permitido",
    "planificar",
    "servir",
]
