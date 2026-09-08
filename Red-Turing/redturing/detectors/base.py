"""
Contrato de un detector: mirar una respuesta y decidir si el ataque penetró.

Un detector devuelve `None` cuando no tiene nada que decir sobre ese caso. Eso
es lo que permite encadenarlos: la cascada recorre los detectores baratos y
determinísticos primero, y solo si ninguno emite un veredicto de confianza alta
paga la llamada al juez LLM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import CasoAtaque, RespuestaObjetivo, Veredicto


class Detector(ABC):
    """Evalúa una respuesta. Devolver None significa 'no me consta'."""

    nombre: str = "detector"

    @abstractmethod
    def evaluar(
        self, caso: CasoAtaque, respuesta: RespuestaObjetivo
    ) -> Optional[Veredicto]:
        ...
