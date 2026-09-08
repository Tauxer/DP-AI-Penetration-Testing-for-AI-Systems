"""
Modelo de datos de Red Turing: caso de ataque, respuesta del objetivo, veredicto e informe.

Todo el sistema se comunica con estas cinco estructuras. Los targets producen
`RespuestaObjetivo`, los detectores producen `Veredicto`, y el runner los une en
`ResultadoAtaque` para construir el `InformeCorrida`.

Convención central e invertida: `exito=True` en un `Veredicto` significa que el
ATAQUE tuvo éxito, es decir, que la defensa falló. Un ASR alto es una mala
noticia, no una buena.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

SEVERIDADES = ("baja", "media", "alta", "critica")
CONFIANZAS = ("baja", "media", "alta")


@dataclass
class CasoAtaque:
    """Un payload adversario y la definición de qué contaría como éxito."""

    id: str
    categoria: str
    tecnica: str
    payload: str
    objetivo: str = ""
    severidad: str = "media"
    benigno: bool = False
    exito_si: Dict[str, Any] = field(default_factory=dict)
    referencia: str = ""
    notas: str = ""
    archivo_origen: str = ""

    def __post_init__(self) -> None:
        if self.severidad not in SEVERIDADES:
            raise ValueError(
                f"Caso '{self.id}': severidad '{self.severidad}' no válida. "
                f"Usa una de {SEVERIDADES}."
            )
        if not self.payload.strip():
            raise ValueError(f"Caso '{self.id}': el payload está vacío.")


@dataclass
class RespuestaObjetivo:
    """Lo que devolvió el sistema atacado."""

    texto: str = ""
    bloqueado: bool = False
    motivo: str = ""
    capa: str = ""
    latencia_ms: float = 0.0
    error: Optional[str] = None
    crudo: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Veredicto:
    """Dictamen de un detector sobre si el ataque penetró la defensa."""

    exito: bool
    confianza: str
    detector: str
    evidencia: str = ""

    def __post_init__(self) -> None:
        if self.confianza not in CONFIANZAS:
            raise ValueError(
                f"Confianza '{self.confianza}' no válida. Usa una de {CONFIANZAS}."
            )

    @property
    def concluyente(self) -> bool:
        """Un veredicto de confianza alta cierra la cascada: no se llama al juez."""
        return self.confianza == "alta"


@dataclass
class ResultadoAtaque:
    """
    Un caso ejecutado contra un objetivo, ya evaluado.

    `veredicto` es el resultado de punta a punta: lo que le pasaría a un
    atacante real (si el guardrail bloquea, el ataque no prosperó).

    `veredicto_llm` mide solo la segunda línea de defensa —el modelo y su system
    prompt— cuando el objetivo también hizo llegar el payload al agente aunque
    el guardrail lo hubiera bloqueado. Responde a la pregunta «si el filtro no
    existiera, ¿cedería el LLM?». Es None cuando no hay texto del agente.
    """

    caso: CasoAtaque
    respuesta: RespuestaObjetivo
    veredicto: Veredicto
    veredicto_llm: Optional[Veredicto] = None

    def a_dict(self) -> Dict[str, Any]:
        return {
            "caso": asdict(self.caso),
            "respuesta": asdict(self.respuesta),
            "veredicto": asdict(self.veredicto),
            "veredicto_llm": asdict(self.veredicto_llm) if self.veredicto_llm else None,
        }


@dataclass
class InformeCorrida:
    """Agregado de una corrida completa, con el ASR ya calculado."""

    objetivo: str
    tipo_objetivo: str
    resultados: List[ResultadoAtaque] = field(default_factory=list)
    inicio: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    duracion_s: float = 0.0
    juez_activo: bool = False

    @property
    def total(self) -> int:
        return len(self.resultados)

    @property
    def exitosos(self) -> List[ResultadoAtaque]:
        """Ataques que penetraron. Esta es la lista que importa."""
        return [r for r in self.resultados if r.veredicto.exito]

    @property
    def errores(self) -> List[ResultadoAtaque]:
        return [r for r in self.resultados if r.respuesta.error]

    @property
    def evaluados(self) -> List[ResultadoAtaque]:
        """Casos con un veredicto real. Excluye los que no se pudieron medir."""
        return [r for r in self.resultados if not r.respuesta.error]

    @property
    def asr(self) -> float:
        """
        Attack Success Rate global, en [0, 1]. Más bajo es mejor.

        Los casos con error quedan FUERA del denominador. Si un objetivo caído
        contara como ataque contenido, bastaría con tumbar el servicio para
        sacar un ASR excelente, y una capa de IA con la cuota agotada haría
        parecer al sistema más seguro justo cuando está más expuesto.
        """
        evaluados = self.evaluados
        if not evaluados:
            return 0.0
        return len(self.exitosos) / len(evaluados)

    def asr_por(self, campo: str) -> Dict[str, Dict[str, Any]]:
        """ASR desglosado por 'categoria', 'tecnica', 'severidad' o 'capa'."""
        grupos: Dict[str, List[ResultadoAtaque]] = {}
        for r in self.evaluados:
            if campo == "capa":
                clave = r.respuesta.capa or "(sin bloqueo)"
            else:
                clave = getattr(r.caso, campo)
            grupos.setdefault(clave, []).append(r)

        salida = {}
        for clave, items in sorted(grupos.items()):
            penetraron = [i for i in items if i.veredicto.exito]
            salida[clave] = {
                "total": len(items),
                "exitosos": len(penetraron),
                "asr": len(penetraron) / len(items) if items else 0.0,
                "ids": [i.caso.id for i in penetraron],
            }
        return salida

    # ── segunda línea de defensa: el LLM sin el guardrail delante ──

    @property
    def evaluados_llm(self) -> List[ResultadoAtaque]:
        """Casos en los que el agente respondió y se pudo juzgar al LLM por separado."""
        return [r for r in self.resultados if r.veredicto_llm is not None and not r.respuesta.error]

    @property
    def cedidos_llm(self) -> List[ResultadoAtaque]:
        """Casos en los que el LLM cedió al ataque, lo haya parado o no el guardrail."""
        return [r for r in self.evaluados_llm if r.veredicto_llm.exito]

    @property
    def asr_llm(self) -> Optional[float]:
        """ASR del LLM solo, en [0, 1]. None si el objetivo no evaluó al LLM aparte."""
        evaluados = self.evaluados_llm
        if not evaluados:
            return None
        return len(self.cedidos_llm) / len(evaluados)

    def asr_llm_por(self, campo: str) -> Dict[str, Dict[str, Any]]:
        grupos: Dict[str, List[ResultadoAtaque]] = {}
        for r in self.evaluados_llm:
            grupos.setdefault(getattr(r.caso, campo), []).append(r)
        salida = {}
        for clave, items in sorted(grupos.items()):
            cedidos = [i for i in items if i.veredicto_llm.exito]
            salida[clave] = {
                "total": len(items),
                "exitosos": len(cedidos),
                "asr": len(cedidos) / len(items) if items else 0.0,
                "ids": [i.caso.id for i in cedidos],
            }
        return salida

    @property
    def latencia_mediana_ms(self) -> float:
        latencias = [r.respuesta.latencia_ms for r in self.resultados if r.respuesta.latencia_ms]
        return statistics.median(latencias) if latencias else 0.0

    def a_dict(self) -> Dict[str, Any]:
        return {
            "objetivo": self.objetivo,
            "tipo_objetivo": self.tipo_objetivo,
            "inicio": self.inicio,
            "duracion_s": round(self.duracion_s, 2),
            "juez_activo": self.juez_activo,
            "resumen": {
                "total": self.total,
                "evaluados": len(self.evaluados),
                "exitosos": len(self.exitosos),
                "errores": len(self.errores),
                "asr": round(self.asr, 4),
                "latencia_mediana_ms": round(self.latencia_mediana_ms, 1),
                "evaluados_llm": len(self.evaluados_llm),
                "cedidos_llm": len(self.cedidos_llm),
                "asr_llm": None if self.asr_llm is None else round(self.asr_llm, 4),
            },
            "asr_llm_por_categoria": self.asr_llm_por("categoria"),
            "asr_por_categoria": self.asr_por("categoria"),
            "asr_por_severidad": self.asr_por("severidad"),
            "asr_por_capa_que_bloqueo": self.asr_por("capa"),
            "resultados": [r.a_dict() for r in self.resultados],
        }
