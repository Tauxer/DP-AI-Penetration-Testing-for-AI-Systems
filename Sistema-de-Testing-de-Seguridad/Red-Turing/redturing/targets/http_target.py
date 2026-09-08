"""
Adaptador genérico para atacar cualquier proyecto expuesto por HTTP.

Es el que hace a Red Turing reutilizable fuera de este módulo: si el sistema
bajo prueba habla JSON por una URL, no hace falta importarlo ni compartir su
entorno de Python. La plantilla del cuerpo y la ruta de la respuesta se
declaran en targets.yaml.

El token de autorización se toma de una VARIABLE DE ENTORNO nombrada en la
config (`env_token`), nunca escrito en el YAML.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List

import requests

from ..models import RespuestaObjetivo
from .base import Objetivo

TIMEOUT_S = 60


def _extraer(datos: Any, ruta: str) -> str:
    """Navega un JSON con una ruta tipo 'choices.0.message.content'."""
    actual = datos
    for tramo in ruta.split("."):
        if isinstance(actual, list):
            actual = actual[int(tramo)]
        elif isinstance(actual, dict):
            actual = actual.get(tramo)
        else:
            return ""
        if actual is None:
            return ""
    return actual if isinstance(actual, str) else json.dumps(actual, ensure_ascii=False)


class ObjetivoHttp(Objetivo):
    tipo = "http"

    def __init__(self, nombre: str, config: Dict[str, Any]):
        super().__init__(nombre, config)
        self.url = config["url"]
        self.metodo = config.get("metodo", "POST").upper()
        self.plantilla_cuerpo = config.get("cuerpo", {"mensaje": "{payload}"})
        self.ruta_respuesta = config.get("ruta_respuesta", "respuesta")
        self.codigos_bloqueo: List[int] = config.get("codigos_bloqueo", [403])

        self.cabeceras = dict(config.get("cabeceras", {}))
        env_token = config.get("env_token")
        if env_token:
            token = os.getenv(env_token)
            if not token:
                raise EnvironmentError(
                    f"El objetivo '{nombre}' requiere la variable de entorno "
                    f"{env_token}, que no está definida."
                )
            plantilla = config.get("plantilla_auth", "Bearer {token}")
            self.cabeceras["Authorization"] = plantilla.format(token=token)

    def _construir_cuerpo(self, payload: str, session_id: str | None = None) -> Any:
        crudo = json.dumps(self.plantilla_cuerpo)
        # json.dumps sobre el payload aporta el escapado correcto y le quita las comillas.
        crudo = crudo.replace("{payload}", json.dumps(payload)[1:-1])
        # {session_id}: una conversación nueva por envío, salvo que el llamador
        # (un ataque multi-turno) pida mantener la misma.
        crudo = crudo.replace("{session_id}", session_id or str(uuid.uuid4()))
        return json.loads(crudo)

    def _invocar(self, payload: str, session_id: str | None = None, **_: Any) -> RespuestaObjetivo:
        r = requests.request(
            self.metodo,
            self.url,
            json=self._construir_cuerpo(payload, session_id),
            headers=self.cabeceras,
            timeout=TIMEOUT_S,
        )

        if r.status_code in self.codigos_bloqueo:
            return RespuestaObjetivo(
                bloqueado=True,
                motivo=f"http_{r.status_code}",
                capa=f"HTTP {r.status_code}",
                crudo={"status": r.status_code, "cuerpo": r.text[:500]},
            )

        r.raise_for_status()
        try:
            datos = r.json()
        except ValueError:
            return RespuestaObjetivo(texto=r.text, crudo={"status": r.status_code})

        return RespuestaObjetivo(
            texto=_extraer(datos, self.ruta_respuesta),
            crudo={"status": r.status_code},
        )
