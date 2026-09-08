"""
Adaptador para atacar SOLO el guardrail de entrada, sin gastar tokens del agente.

Espera una función con la firma `(mensaje: str) -> (bool, str)` donde el bool
indica si el mensaje es seguro. Es el objetivo barato: corre en milisegundos
por caso salvo las capas que llaman a Groq, y responde una única pregunta —
¿este payload entra o no entra? No detecta nada de lo que pase después.
"""

from __future__ import annotations

from typing import Any, Dict

from ..models import RespuestaObjetivo
from .base import MOTIVOS_NO_CONCLUYENTES, Objetivo, cargar_callable, nombre_de_capa


class ObjetivoGuardrail(Objetivo):
    tipo = "guardrail"

    def __init__(self, nombre: str, config: Dict[str, Any]):
        super().__init__(nombre, config)
        self._verificar = cargar_callable(
            config["ruta_proyecto"],
            config.get("modulo", "guardrails.input_guardrail"),
            config.get("funcion", "verificar_input_guardrail"),
        )

    def _invocar(self, payload: str, **_: Any) -> RespuestaObjetivo:
        es_seguro, motivo = self._verificar(payload)
        bloqueado = not es_seguro

        # Un bloqueo por servicio caído no dice nada sobre el payload. Se marca
        # como error para que quede fuera del ASR en lugar de contar como acierto.
        error = None
        if bloqueado and motivo in MOTIVOS_NO_CONCLUYENTES:
            error = (
                f"No concluyente: la capa de IA bloqueó por '{motivo}' "
                "(fail-close), no por el contenido del payload."
            )

        return RespuestaObjetivo(
            texto="",
            bloqueado=bloqueado,
            motivo=motivo,
            capa=nombre_de_capa(motivo) if bloqueado else "",
            error=error,
            crudo={"es_seguro": es_seguro, "motivo": motivo},
        )
