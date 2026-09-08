"""
Informe JSON: el artefacto que se versiona y se compara entre corridas.

Es la salida que hace de Red Turing un test de regresión y no solo una foto.
Guardando el JSON de cada corrida se puede responder la pregunta que importa
tras cada cambio del guardrail: ¿qué ataque que antes parábamos ahora entra?
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ..models import InformeCorrida


def guardar_json(informe: InformeCorrida, directorio: Path) -> Path:
    directorio.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    ruta = directorio / f"redturing-{informe.objetivo}-{marca}.json"
    ruta.write_text(
        json.dumps(informe.a_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return ruta


def comparar(anterior: Path, actual: InformeCorrida) -> Dict[str, List[str]]:
    """
    Diferencia entre una corrida guardada y la actual.

    'regresiones' son ataques que antes se paraban y ahora entran — el dato por
    el que existe este módulo. Exigen que el caso se haya medido en ambas
    corridas; los que antes fallaron por servicio caído van en 'primera_medicion'.
    """
    previo = json.loads(anterior.read_text(encoding="utf-8"))
    antes_todo = {r["caso"]["id"]: r for r in previo.get("resultados", [])}
    ahora_todo = {r.caso.id: r for r in actual.resultados}

    antes = {i: r["veredicto"]["exito"] for i, r in antes_todo.items() if not r.get("respuesta", {}).get("error")}
    ahora = {i: r.veredicto.exito for i, r in ahora_todo.items() if not r.respuesta.error}
    comunes = set(antes) & set(ahora)

    return {
        "regresiones": sorted(i for i in comunes if ahora[i] and not antes[i]),
        "corregidos": sorted(i for i in comunes if antes[i] and not ahora[i]),
        "casos_nuevos": sorted(set(ahora_todo) - set(antes_todo)),
        "casos_retirados": sorted(set(antes_todo) - set(ahora_todo)),
        "primera_medicion": sorted(i for i in set(antes_todo) & set(ahora) if i not in antes),
    }
