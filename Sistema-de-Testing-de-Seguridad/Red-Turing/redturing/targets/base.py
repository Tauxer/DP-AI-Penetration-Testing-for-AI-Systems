"""
Contrato que todo objetivo atacable debe cumplir, más el cargador de proyectos externos.

Red Turing no sabe nada de LangChain, de Chatwoot ni de tu arquitectura: solo
sabe mandar un texto y recibir un `RespuestaObjetivo`. Cada adaptador concreto
(guardrail, agente, HTTP) traduce entre ese contrato y el sistema real.

Los objetivos in-process se importan con `importlib` tras insertar la raíz del
proyecto objetivo en `sys.path` y cargar SU archivo .env, porque el guardrail y
el agente leen credenciales al importarse. Los valores de esas credenciales
nunca se leen ni se imprimen aquí: solo se cargan al entorno del proceso.
"""

from __future__ import annotations

import importlib
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict

from dotenv import load_dotenv

from ..models import RespuestaObjetivo

# Traduce el motivo de bloqueo del guardrail al nombre legible de la capa,
# para que el informe diga QUÉ defensa paró el ataque y no solo que lo paró.
CAPAS_POR_MOTIVO: Dict[str, str] = {
    "clave_secreta": "C1 Secret Keys (regex)",
    "prompt_injection": "C2 Prompt Injection (regex)",
    "recon_infraestructura": "C2 Recon Infraestructura (regex)",
    "contenido_toxico": "C3 Toxic Patterns (regex)",
    "patron_personalizado": "C4 Custom Regex",
    "pii_detectado": "C5 PII / Presidio",
    "url_detectada": "C6 URL Filter",
    "dominio_bloqueado": "C6 Dominio Bloqueado",
    "jailbreak": "C7 Llama Prompt Guard 2",
    "jailbreak_ia": "C7 Llama Prompt Guard 2",
    "toxicidad": "C8 GPT-OSS-Safeguard",
    "contenido_ia_bloqueado": "C8 GPT-OSS-Safeguard",
    "servicio_no_disponible": "C7/C8 fail-close (servicio caído)",
}

# Un fail-close no es una defensa que funcione: es una defensa que no pudo
# opinar. Contarlo como bloqueo legítimo inflaría la seguridad aparente del
# sistema justo cuando su capa de IA está caída o limitada por cuota.
MOTIVOS_NO_CONCLUYENTES = frozenset({"servicio_no_disponible"})


def nombre_de_capa(motivo: str) -> str:
    """Nombre legible de la capa que bloqueó, o el motivo crudo si es desconocido."""
    if not motivo:
        return ""
    return CAPAS_POR_MOTIVO.get(motivo, f"otra ({motivo})")


def cargar_callable(ruta_proyecto: str, modulo: str, funcion: str) -> Callable[..., Any]:
    """
    Importa `funcion` desde `modulo` dentro de un proyecto externo.

    Inserta la raíz del proyecto en sys.path y carga su .env antes de importar,
    porque los módulos de seguridad suelen instanciar singletons al importarse.
    """
    raiz = Path(ruta_proyecto).expanduser().resolve()
    if not raiz.is_dir():
        raise FileNotFoundError(f"El proyecto objetivo no existe: {raiz}")

    archivo_env = raiz / ".env"
    if archivo_env.is_file():
        load_dotenv(archivo_env, override=False)

    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))

    try:
        mod = importlib.import_module(modulo)
    except ImportError as e:
        raise ImportError(
            f"No se pudo importar '{modulo}' desde {raiz}. "
            f"Comprueba que las dependencias del proyecto objetivo estén instaladas "
            f"en este mismo entorno virtual. Error original: {e}"
        ) from e

    if not hasattr(mod, funcion):
        raise AttributeError(f"'{modulo}' no expone '{funcion}'.")

    return getattr(mod, funcion)


class Objetivo(ABC):
    """Sistema bajo prueba. Un adaptador por forma de invocación."""

    tipo: str = "base"

    def __init__(self, nombre: str, config: Dict[str, Any]):
        self.nombre = nombre
        self.config = config

    @abstractmethod
    def _invocar(self, payload: str, **opciones: Any) -> RespuestaObjetivo:
        """Manda el payload al sistema real. Puede lanzar excepciones."""

    def enviar(self, payload: str, **opciones: Any) -> RespuestaObjetivo:
        """
        Invoca el objetivo midiendo latencia y capturando fallos como error.

        `opciones` viaja al adaptador. Hoy solo se usa `session_id`, para que un
        ataque multi-turno (DeepTeam) mantenga la misma conversación: sin él,
        cada envío es una sesión nueva, que es lo correcto para Red Turing.
        """
        inicio = time.perf_counter()
        try:
            respuesta = self._invocar(payload, **opciones)
        except Exception as e:  # noqa: BLE001 — un objetivo caído no debe tumbar la corrida
            respuesta = RespuestaObjetivo(error=f"{type(e).__name__}: {e}")
        respuesta.latencia_ms = (time.perf_counter() - inicio) * 1000
        return respuesta
