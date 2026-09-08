"""
Registro de objetivos: traduce una entrada de `targets.yaml` en un adaptador vivo.

Añadir un tipo de objetivo nuevo es escribir una subclase de `Objetivo` y
registrarla en TIPOS. Nada más en el sistema necesita enterarse.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Type

import yaml

from .base import Objetivo
from .agent_target import ObjetivoAgente
from .fake_target import ObjetivoSimulado
from .guardrail_target import ObjetivoGuardrail
from .http_target import ObjetivoHttp

RUTA_CONFIG = Path(__file__).resolve().parent.parent.parent / "targets.yaml"

TIPOS: Dict[str, Type[Objetivo]] = {
    "guardrail": ObjetivoGuardrail,
    "agente": ObjetivoAgente,
    "http": ObjetivoHttp,
    "simulado": ObjetivoSimulado,
}


def _resolver_rutas(config: Dict[str, Any], base: Path) -> Dict[str, Any]:
    """Las rutas relativas del YAML se interpretan desde la raíz de Red Turing."""
    if "ruta_proyecto" in config:
        ruta = Path(config["ruta_proyecto"]).expanduser()
        if not ruta.is_absolute():
            ruta = (base / ruta).resolve()
        config = {**config, "ruta_proyecto": str(ruta)}
    return config


def leer_config(ruta: Path = RUTA_CONFIG) -> Dict[str, Dict[str, Any]]:
    """Devuelve el mapa de objetivos declarados."""
    if not ruta.is_file():
        raise FileNotFoundError(
            f"Falta {ruta.name}. Copia targets.example.yaml y ajústalo a tus proyectos."
        )
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    return datos.get("targets", {})


def construir_objetivo(nombre: str, ruta_config: Path = RUTA_CONFIG) -> Objetivo:
    """Instancia el adaptador declarado bajo `nombre` en targets.yaml."""
    objetivos = leer_config(ruta_config)
    if nombre not in objetivos:
        raise KeyError(
            f"Objetivo '{nombre}' no declarado en {ruta_config.name}. "
            f"Disponibles: {', '.join(sorted(objetivos)) or '(ninguno)'}"
        )

    config = _resolver_rutas(objetivos[nombre], ruta_config.parent)
    tipo = config.get("tipo")
    if tipo not in TIPOS:
        raise ValueError(
            f"Objetivo '{nombre}': tipo '{tipo}' desconocido. "
            f"Tipos válidos: {', '.join(sorted(TIPOS))}"
        )

    return TIPOS[tipo](nombre, config)


__all__ = [
    "Objetivo",
    "ObjetivoAgente",
    "ObjetivoGuardrail",
    "ObjetivoHttp",
    "ObjetivoSimulado",
    "TIPOS",
    "construir_objetivo",
    "leer_config",
]
