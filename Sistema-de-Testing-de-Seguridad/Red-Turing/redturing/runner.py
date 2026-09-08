"""
Orquestador de una corrida: manda cada payload al objetivo y evalúa la respuesta.

Una corrida no se detiene ante un fallo. Si el objetivo se cae en el caso 12, ese
caso queda marcado como error y los 80 restantes siguen ejecutándose: un informe
parcial sirve, una traza a mitad de camino no.

La ejecución es concurrente por defecto porque las capas de IA del guardrail y el
agente son dominados por latencia de red. Cada caso usa su propia sesión, así que
el orden no altera el resultado.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Callable, List, Optional

from .detectors import CascadaDetectores
from .models import CasoAtaque, InformeCorrida, ResultadoAtaque
from .targets.base import Objetivo

WORKERS_POR_DEFECTO = 4


def ejecutar_corrida(
    objetivo: Objetivo,
    casos: List[CasoAtaque],
    usar_juez: bool = True,
    workers: int = WORKERS_POR_DEFECTO,
    al_terminar_caso: Optional[Callable[[ResultadoAtaque, int, int], None]] = None,
    debe_parar: Optional[Callable[[], bool]] = None,
) -> InformeCorrida:
    """
    Lanza `casos` contra `objetivo` y devuelve el informe con el ASR calculado.

    `al_terminar_caso` recibe (resultado, indice_1based, total) para pintar
    progreso en vivo sin que el runner sepa nada de la interfaz.

    `debe_parar` es la cancelación cooperativa: se consulta antes de enviar cada
    payload. Cuando devuelve True, los casos que aún no salieron se omiten (no
    se le manda nada más al objetivo) y los que ya están en vuelo terminan y se
    incluyen. El informe resultante es parcial y honesto: solo contiene casos
    que de verdad se midieron.
    """
    cascada = CascadaDetectores(usar_juez=usar_juez, tipo_objetivo=objetivo.tipo)
    informe = InformeCorrida(
        objetivo=objetivo.nombre,
        tipo_objetivo=objetivo.tipo,
        juez_activo=cascada.juez_activo,
    )

    total = len(casos)
    inicio = time.perf_counter()

    def procesar(caso: CasoAtaque) -> Optional[ResultadoAtaque]:
        if debe_parar and debe_parar():
            return None  # cancelado antes de salir: no cuenta ni como error
        respuesta = objetivo.enviar(caso.payload)
        # Punta a punta: si el guardrail bloqueó, el atacante real nunca ve lo que
        # el modelo hubiera dicho. Esa respuesta se juzga aparte, no aquí.
        vista_atacante = respuesta
        if respuesta.bloqueado and respuesta.texto and respuesta.crudo.get("llm_pese_al_bloqueo"):
            vista_atacante = replace(respuesta, texto="")
        veredicto = cascada.evaluar(caso, vista_atacante)
        # Segunda línea de defensa: el LLM solo, con el texto que sí produjo.
        # Sin bloqueo, ambos veredictos coinciden.
        veredicto_llm = cascada.evaluar_llm(caso, respuesta) if respuesta.texto else None
        return ResultadoAtaque(
            caso=caso, respuesta=respuesta, veredicto=veredicto, veredicto_llm=veredicto_llm
        )

    if workers <= 1:
        iterador = (procesar(caso) for caso in casos)
    else:
        ejecutor = ThreadPoolExecutor(max_workers=workers)
        iterador = ejecutor.map(procesar, casos)

    try:
        for i, resultado in enumerate(iterador, start=1):
            if resultado is None:
                continue
            informe.resultados.append(resultado)
            if al_terminar_caso:
                al_terminar_caso(resultado, i, total)
    finally:
        if workers > 1:
            ejecutor.shutdown(wait=True)

    informe.duracion_s = time.perf_counter() - inicio
    return informe
