"""
Interfaz de línea de comandos de Red Turing.

Ejecutar:
    python -m redturing objetivos
    python -m redturing suites
    python -m redturing correr --objetivo guardrail-databot --suite all
    python -m redturing correr --objetivo agente-databot --suite jailbreak --limite 5
    python -m redturing dashboard      # ver corridas y lanzar nuevas desde el navegador

El código de salida es lo que permite usarlo en CI: 0 si el ASR queda bajo el
umbral, 1 si lo supera o si aparecen regresiones, 2 si la configuración está mal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from .loader import cargar_suites, filtrar_casos, listar_suites
from .models import CasoAtaque
from .report import (
    comparar,
    guardar_html,
    guardar_json,
    imprimir_cabecera,
    imprimir_resumen,
    progreso,
)
from .runner import WORKERS_POR_DEFECTO, ejecutar_corrida
from .targets import construir_objetivo, leer_config

RAIZ = Path(__file__).resolve().parent.parent
DIRECTORIO_INFORMES = RAIZ / "reports"

SALIDA_OK = 0
SALIDA_FALLO = 1
SALIDA_CONFIG = 2


def _filtrar(casos: List[CasoAtaque], args) -> List[CasoAtaque]:
    return filtrar_casos(
        casos,
        severidad=args.severidad,
        categorias=args.categoria.split(",") if args.categoria else None,
        limite=args.limite,
    )


def cmd_objetivos(args) -> int:
    try:
        objetivos = leer_config()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return SALIDA_CONFIG

    if not objetivos:
        print("No hay objetivos declarados en targets.yaml.")
        return SALIDA_OK

    print("\nObjetivos declarados en targets.yaml:\n")
    for nombre, config in sorted(objetivos.items()):
        destino = config.get("ruta_proyecto") or config.get("url", "")
        print(f"  {nombre:<26} [{config.get('tipo', '?')}]  {destino}")
    print()
    return SALIDA_OK


def cmd_suites(args) -> int:
    suites = listar_suites()
    print("\nSuites de ataque disponibles:\n")
    for nombre, cantidad in sorted(suites.items()):
        print(f"  {nombre:<26} {cantidad:>3} casos")
    print(f"\n  {'TOTAL':<26} {sum(suites.values()):>3} casos\n")
    return SALIDA_OK


def cmd_casos(args) -> int:
    suites = args.suite.split(",") if args.suite else None
    for caso in cargar_suites(suites):
        print(f"  [{caso.severidad:<7}] {caso.id:<30} {caso.categoria}/{caso.tecnica}")
    return SALIDA_OK


def cmd_correr(args) -> int:
    try:
        objetivo = construir_objetivo(args.objetivo)
    except (FileNotFoundError, KeyError, ValueError, ImportError, EnvironmentError) as e:
        print(f"Error de configuración: {e}", file=sys.stderr)
        return SALIDA_CONFIG

    suites = args.suite.split(",") if args.suite else None
    try:
        casos = _filtrar(cargar_suites(suites), args)
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"Error cargando ataques: {e}", file=sys.stderr)
        return SALIDA_CONFIG

    if not casos:
        print("Ningún caso coincide con los filtros indicados.", file=sys.stderr)
        return SALIDA_CONFIG

    from .detectors import CascadaDetectores

    sonda = CascadaDetectores(usar_juez=not args.sin_juez, tipo_objetivo=objetivo.tipo)
    estado_juez = "activo" if sonda.juez_activo else f"inactivo ({sonda.motivo_juez_inactivo})"

    imprimir_cabecera(objetivo.nombre, objetivo.tipo, len(casos), estado_juez)

    informe = ejecutar_corrida(
        objetivo=objetivo,
        casos=casos,
        usar_juez=not args.sin_juez,
        workers=args.workers,
        al_terminar_caso=None if args.silencioso else progreso,
    )

    imprimir_resumen(informe)

    ruta_json = guardar_json(informe, DIRECTORIO_INFORMES)
    print(f"  Informe JSON : {ruta_json.relative_to(RAIZ)}")
    if not args.sin_html:
        ruta_html = guardar_html(informe, DIRECTORIO_INFORMES)
        print(f"  Informe HTML : {ruta_html.relative_to(RAIZ)}")

    salida = SALIDA_OK

    if args.comparar:
        anterior = Path(args.comparar)
        if not anterior.is_file():
            print(f"\n  Aviso: no existe {anterior}, se omite la comparación.")
        else:
            diff = comparar(anterior, informe)
            print(f"\n  Comparado con {anterior.name}:")
            print(f"    regresiones   : {', '.join(diff['regresiones']) or 'ninguna'}")
            print(f"    corregidos    : {', '.join(diff['corregidos']) or 'ninguno'}")
            print(f"    casos nuevos  : {len(diff['casos_nuevos'])}")
            if diff["primera_medicion"]:
                print(f"    1ª medición   : {len(diff['primera_medicion'])} (antes con error, no cuentan como regresión)")
            if diff["regresiones"]:
                print("\n  FALLO: hay ataques que antes se detenían y ahora penetran.")
                salida = SALIDA_FALLO

    if informe.asr > args.umbral_asr:
        print(
            f"\n  FALLO: ASR {informe.asr:.1%} supera el umbral "
            f"{args.umbral_asr:.1%}."
        )
        salida = SALIDA_FALLO

    print()
    return salida


def cmd_dashboard(args) -> int:
    from .dashboard import servir

    servir(puerto=args.puerto, abrir=not args.sin_abrir)
    return SALIDA_OK


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redturing",
        description="Red Turing — test adversario de sistemas LLM (jailbreak, prompt injection).",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("objetivos", help="Lista los objetivos de targets.yaml").set_defaults(
        func=cmd_objetivos
    )
    sub.add_parser("suites", help="Lista las suites de ataque").set_defaults(func=cmd_suites)

    p_casos = sub.add_parser("casos", help="Lista los casos de una o varias suites")
    p_casos.add_argument("--suite", help="Suites separadas por coma (por defecto: todas)")
    p_casos.set_defaults(func=cmd_casos)

    p_run = sub.add_parser("correr", help="Lanza una corrida contra un objetivo")
    p_run.add_argument("--objetivo", required=True, help="Nombre declarado en targets.yaml")
    p_run.add_argument("--suite", help="Suites separadas por coma (por defecto: todas)")
    p_run.add_argument("--categoria", help="Filtra por categorías separadas por coma")
    p_run.add_argument(
        "--severidad",
        choices=["baja", "media", "alta", "critica"],
        help="Ejecuta solo casos de esta severidad hacia arriba",
    )
    p_run.add_argument("--limite", type=int, help="Máximo de casos a ejecutar")
    p_run.add_argument(
        "--workers", type=int, default=WORKERS_POR_DEFECTO, help="Ataques en paralelo (1 = secuencial)"
    )
    p_run.add_argument("--sin-juez", action="store_true", help="Solo detectores determinísticos")
    p_run.add_argument("--sin-html", action="store_true", help="No generar el informe HTML")
    p_run.add_argument("--silencioso", action="store_true", help="Oculta el progreso caso a caso")
    p_run.add_argument(
        "--umbral-asr",
        type=float,
        default=1.0,
        help="Sale con código 1 si el ASR lo supera. Para CI, prueba 0.0",
    )
    p_run.add_argument("--comparar", help="Ruta a un informe JSON previo para detectar regresiones")
    p_run.set_defaults(func=cmd_correr)

    p_dash = sub.add_parser("dashboard", help="Abre el dashboard local: corridas, comparación y lanzador")
    p_dash.add_argument("--puerto", type=int, default=8731, help="Puerto en localhost (8731)")
    p_dash.add_argument("--sin-abrir", action="store_true", help="No abrir el navegador automáticamente")
    p_dash.set_defaults(func=cmd_dashboard)

    return parser


def main(argv: List[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
