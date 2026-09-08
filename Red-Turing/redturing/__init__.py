"""
Red Turing — sistema de testing adversario para proyectos con LLM.

Un test de Turing invertido: en lugar de comprobar si una máquina pasa por
humana, comprueba si un humano hostil puede hacer que la máquina deje de
comportarse como se le ordenó.

Uso como librería:
    from redturing import cargar_suites, construir_objetivo, ejecutar_corrida

    objetivo = construir_objetivo("guardrail-databot")
    informe = ejecutar_corrida(objetivo, cargar_suites(["jailbreak"]))
    print(informe.asr)
"""

from .loader import cargar_suites, listar_suites
from .models import CasoAtaque, InformeCorrida, RespuestaObjetivo, ResultadoAtaque, Veredicto
from .runner import ejecutar_corrida
from .targets import construir_objetivo

__version__ = "0.1.0"

__all__ = [
    "CasoAtaque",
    "InformeCorrida",
    "RespuestaObjetivo",
    "ResultadoAtaque",
    "Veredicto",
    "cargar_suites",
    "construir_objetivo",
    "ejecutar_corrida",
    "listar_suites",
]
