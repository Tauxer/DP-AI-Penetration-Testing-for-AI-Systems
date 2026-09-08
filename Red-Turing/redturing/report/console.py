"""
Salida por terminal: progreso en vivo y resumen final con el ASR por categoría.

El informe se lee de arriba abajo en orden de urgencia: primero el veredicto
global, después qué categorías fallan, después la lista nominal de ataques que
penetraron. Lo que no penetró no se lista; ocupa espacio y no requiere acción.

Sin dependencias de terceros: colores ANSI y desactivación automática cuando la
salida no es una terminal, para que el log de CI quede limpio.
"""

from __future__ import annotations

import sys

from ..models import InformeCorrida, ResultadoAtaque

_COLOR = sys.stdout.isatty()

ROJO = "\033[31m" if _COLOR else ""
VERDE = "\033[32m" if _COLOR else ""
AMARILLO = "\033[33m" if _COLOR else ""
GRIS = "\033[90m" if _COLOR else ""
NEGRITA = "\033[1m" if _COLOR else ""
FIN = "\033[0m" if _COLOR else ""

ANCHO = 78
ICONO_SEVERIDAD = {"critica": "!!", "alta": "! ", "media": "· ", "baja": "  "}


def _regla(caracter: str = "─") -> str:
    return caracter * ANCHO


def imprimir_cabecera(objetivo: str, tipo: str, total: int, juez: str) -> None:
    print(f"\n{NEGRITA}RED TURING{FIN} {GRIS}— test adversario de LLM{FIN}")
    print(_regla("═"))
    print(f"  Objetivo : {NEGRITA}{objetivo}{FIN} ({tipo})")
    print(f"  Ataques  : {total}")
    print(f"  Juez LLM : {juez}")
    print(_regla("═"))


def progreso(resultado: ResultadoAtaque, i: int, total: int) -> None:
    """Una línea por caso, conforme terminan."""
    if resultado.respuesta.error:
        marca, color = "ERR ", AMARILLO
    elif resultado.veredicto.exito:
        marca, color = "PASA", ROJO
    else:
        marca, color = "PARA", VERDE

    sev = ICONO_SEVERIDAD.get(resultado.caso.severidad, "  ")
    nota = resultado.respuesta.capa or resultado.veredicto.detector
    print(
        f"  {GRIS}[{i:>3}/{total}]{FIN} {color}{marca}{FIN} {sev} "
        f"{resultado.caso.id:<28} {GRIS}{nota[:28]}{FIN}"
    )


def _barra(asr: float, ancho: int = 20) -> str:
    llenos = round(asr * ancho)
    color = VERDE if asr == 0 else (AMARILLO if asr < 0.25 else ROJO)
    return f"{color}{'█' * llenos}{GRIS}{'░' * (ancho - llenos)}{FIN}"


def imprimir_resumen(informe: InformeCorrida) -> None:
    asr = informe.asr
    color_asr = VERDE if asr == 0 else (AMARILLO if asr < 0.25 else ROJO)

    print(f"\n{_regla('═')}")
    print(f"{NEGRITA}  RESULTADO{FIN}")
    print(_regla())
    print(
        f"  ASR global      {color_asr}{NEGRITA}{asr:>6.1%}{FIN}  "
        f"{_barra(asr)}  ({len(informe.exitosos)}/{len(informe.evaluados)} penetraron)"
    )
    if informe.errores:
        print(
            f"  {AMARILLO}No evaluados{FIN}    {len(informe.errores)} de {informe.total} "
            f"{GRIS}(fuera del ASR: no se pudo medir){FIN}"
        )
    if informe.asr_llm is not None:
        asr_llm = informe.asr_llm
        color_llm = VERDE if asr_llm == 0 else (AMARILLO if asr_llm < 0.25 else ROJO)
        print(
            f"  ASR solo LLM    {color_llm}{NEGRITA}{asr_llm:>6.1%}{FIN}  "
            f"{_barra(asr_llm)}  ({len(informe.cedidos_llm)}/{len(informe.evaluados_llm)} cedió el modelo)"
        )
        print(f"  {GRIS}(segunda línea de defensa: el modelo y su system prompt, como si el guardrail no existiera){FIN}")
    print(f"  {GRIS}Duración {informe.duracion_s:.1f}s · mediana {informe.latencia_mediana_ms:.0f} ms/caso{FIN}")

    print(f"\n{NEGRITA}  ASR POR CATEGORÍA{FIN}")
    print(_regla())
    for categoria, datos in sorted(
        informe.asr_por("categoria").items(), key=lambda x: -x[1]["asr"]
    ):
        print(
            f"  {categoria:<26} {datos['asr']:>6.1%}  {_barra(datos['asr'], 14)}  "
            f"{GRIS}{datos['exitosos']}/{datos['total']}{FIN}"
        )

    if informe.asr_llm is not None:
        print(f"\n{NEGRITA}  ASR SOLO LLM POR CATEGORÍA{FIN}")
        print(_regla())
        for categoria, datos in sorted(informe.asr_llm_por("categoria").items(), key=lambda x: -x[1]["asr"]):
            print(
                f"  {categoria:<26} {datos['asr']:>6.1%}  {_barra(datos['asr'], 14)}  "
                f"{GRIS}{datos['exitosos']}/{datos['total']}{FIN}"
            )
        cedidos_tapados = [r for r in informe.cedidos_llm if r.respuesta.bloqueado]
        if cedidos_tapados:
            print(f"\n{AMARILLO}{NEGRITA}  EL GUARDRAIL TAPÓ FALLOS DEL PROMPT{FIN}")
            print(f"  {GRIS}El filtro los paró, pero el modelo habría cedido. Son mejoras pendientes del system prompt.{FIN}")
            for r in cedidos_tapados:
                print(f"  {AMARILLO}▸{FIN} {r.caso.id:<32} {GRIS}{r.veredicto_llm.evidencia[:90]}{FIN}")

    capas = {k: v for k, v in informe.asr_por("capa").items() if k != "(sin bloqueo)"}
    if capas:
        print(f"\n{NEGRITA}  QUÉ CAPA DETUVO CADA ATAQUE{FIN}")
        print(_regla())
        for capa, datos in sorted(capas.items(), key=lambda x: -x[1]["total"]):
            print(f"  {capa:<40} {GRIS}{datos['total']} bloqueos{FIN}")

    if informe.exitosos:
        print(f"\n{ROJO}{NEGRITA}  ATAQUES QUE PENETRARON{FIN}")
        print(_regla())
        orden = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
        for r in sorted(informe.exitosos, key=lambda x: orden.get(x.caso.severidad, 9)):
            print(f"\n  {ROJO}▸{FIN} {NEGRITA}{r.caso.id}{FIN}  {GRIS}[{r.caso.severidad}] {r.caso.categoria} / {r.caso.tecnica}{FIN}")
            print(f"    objetivo  : {r.caso.objetivo or '(sin declarar)'}")
            print(f"    evidencia : {r.veredicto.evidencia[:160]}")
            print(f"    detector  : {r.veredicto.detector} (confianza {r.veredicto.confianza})")
            if r.respuesta.texto:
                extracto = " ".join(r.respuesta.texto.split())[:200]
                print(f"    {GRIS}respuesta : {extracto}…{FIN}")
    else:
        print(f"\n{VERDE}{NEGRITA}  Ningún ataque penetró.{FIN}")
        print(f"  {GRIS}Eso no significa que el sistema sea seguro: significa que resiste{FIN}")
        print(f"  {GRIS}esta corpus. Añade vectores nuevos en attacks/ y vuelve a correr.{FIN}")

    print(f"\n{_regla('═')}\n")
