"""Salidas del informe: terminal, JSON versionable y HTML autocontenido."""

from .console import imprimir_cabecera, imprimir_resumen, progreso
from .html_report import guardar_html
from .json_report import comparar, guardar_json

__all__ = [
    "comparar",
    "guardar_html",
    "guardar_json",
    "imprimir_cabecera",
    "imprimir_resumen",
    "progreso",
]
