"""
Carga y valida las suites de ataque en YAML del directorio `attacks/`.

Los payloads viven como datos, no como código: así la corpus crece sin tocar el
runner, y un `git diff` sobre `attacks/` muestra exactamente qué vectores nuevos
se añadieron entre dos versiones del sistema.

El loader falla ruidosamente ante un YAML mal formado o un id duplicado — un id
repetido arruinaría el informe silenciosamente al pisar resultados.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

from .models import CasoAtaque, SEVERIDADES

DIRECTORIO_ATAQUES = Path(__file__).resolve().parent.parent / "attacks"


def _campos_comunes(datos: dict) -> dict:
    """Extrae los valores por defecto que la suite aplica a todos sus casos."""
    return {
        "categoria": datos.get("categoria", "sin_categoria"),
        "severidad": datos.get("severidad", "media"),
        "referencia": datos.get("referencia", ""),
        "benigno": datos.get("benigno", False),
    }


def cargar_archivo(ruta: Path) -> List[CasoAtaque]:
    """Lee un YAML de suite y devuelve sus casos ya validados."""
    with ruta.open(encoding="utf-8") as f:
        datos = yaml.safe_load(f)

    if not isinstance(datos, dict) or "casos" not in datos:
        raise ValueError(f"{ruta.name}: se esperaba un mapa con la clave 'casos'.")

    comunes = _campos_comunes(datos)
    casos: List[CasoAtaque] = []

    for i, crudo in enumerate(datos["casos"]):
        if not isinstance(crudo, dict):
            raise ValueError(f"{ruta.name}: el caso #{i} no es un mapa.")
        combinado = {**comunes, **crudo, "archivo_origen": ruta.name}
        desconocidos = set(combinado) - set(CasoAtaque.__dataclass_fields__)
        if desconocidos:
            raise ValueError(
                f"{ruta.name}, caso '{crudo.get('id', i)}': "
                f"campos no reconocidos {sorted(desconocidos)}."
            )
        casos.append(CasoAtaque(**combinado))

    return casos


def cargar_suites(
    suites: Optional[Iterable[str]] = None,
    directorio: Path = DIRECTORIO_ATAQUES,
) -> List[CasoAtaque]:
    """
    Carga las suites pedidas por nombre de archivo sin extensión.

    `suites=None` o `["all"]` carga todo el directorio.
    """
    if not directorio.is_dir():
        raise FileNotFoundError(f"No existe el directorio de ataques: {directorio}")

    disponibles = {p.stem: p for p in sorted(directorio.glob("*.yaml"))}
    if not disponibles:
        raise FileNotFoundError(f"No hay suites .yaml en {directorio}")

    if suites is None or "all" in suites:
        elegidas = list(disponibles.values())
    else:
        elegidas = []
        for nombre in suites:
            if nombre not in disponibles:
                raise KeyError(
                    f"Suite '{nombre}' no encontrada. "
                    f"Disponibles: {', '.join(sorted(disponibles))}"
                )
            elegidas.append(disponibles[nombre])

    casos: List[CasoAtaque] = []
    vistos: Dict[str, str] = {}
    for ruta in elegidas:
        for caso in cargar_archivo(ruta):
            if caso.id in vistos:
                raise ValueError(
                    f"Id de caso duplicado '{caso.id}': aparece en "
                    f"{vistos[caso.id]} y en {caso.archivo_origen}."
                )
            vistos[caso.id] = caso.archivo_origen
            casos.append(caso)

    return casos


def listar_suites(directorio: Path = DIRECTORIO_ATAQUES) -> Dict[str, int]:
    """Nombre de cada suite disponible y cuántos casos contiene."""
    return {p.stem: len(cargar_archivo(p)) for p in sorted(directorio.glob("*.yaml"))}


def filtrar_casos(
    casos: List[CasoAtaque],
    severidad: Optional[str] = None,
    categorias: Optional[Iterable[str]] = None,
    limite: Optional[int] = None,
) -> List[CasoAtaque]:
    """
    Aplica los filtros de una corrida: severidad mínima, categorías y límite.

    Es la única implementación; la usan el CLI y el dashboard para que ambos
    lancen exactamente los mismos casos ante los mismos parámetros. `severidad`
    es un piso: 'alta' incluye alta y crítica.
    """
    if severidad:
        if severidad not in SEVERIDADES:
            raise ValueError(f"Severidad '{severidad}' no válida. Usa una de {SEVERIDADES}.")
        minimo = SEVERIDADES.index(severidad)
        casos = [c for c in casos if SEVERIDADES.index(c.severidad) >= minimo]
    if categorias:
        pedidas = {c.strip() for c in categorias if c and c.strip()}
        if pedidas:
            casos = [c for c in casos if c.categoria in pedidas]
    if limite is not None:
        if limite < 1:
            raise ValueError("El límite debe ser un entero positivo.")
        casos = casos[:limite]
    return casos
