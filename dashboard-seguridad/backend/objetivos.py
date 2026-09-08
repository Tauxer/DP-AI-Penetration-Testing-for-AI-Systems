"""
Registro de objetivos (los agentes que se van a probar), compartido por Red
Turing y DeepTeam.

La fuente de verdad es `Red-Turing/targets.yaml`: así lo que se registra desde
el dashboard sirve también para el CLI de Red Turing. Cada objetivo tiene un
tipo:

- `http`      — un agente desplegado detrás de una URL (FastAPI, n8n, lo que sea).
                 Es el caso normal en un equipo: no hace falta el código.
- `agente`    — un agente Python importable desde este proceso (TramiBot hoy).
- `guardrail` — solo el filtro de entrada de un proyecto Python.
- `simulado`  — objetivo de mentira para verificar el arnés.

Además de lo que Red Turing necesita, cada objetivo guarda `descripcion` y
`proposito`. El propósito es el párrafo que DeepTeam entrega al adversario para
que invente ataques creíbles; Red Turing lo ignora.

Los secretos NUNCA se guardan aquí: para un endpoint con token se anota el
NOMBRE de la variable de entorno (`env_token`) y el backend la lee del entorno.

Al guardar se reescribe el YAML completo: los comentarios manuales del archivo
se pierden. El archivo lleva una cabecera que lo avisa.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

RAIZ_MODULO = Path(__file__).resolve().parent.parent.parent
RAIZ_REDTURING = RAIZ_MODULO / "Red-Turing"
RUTA_TARGETS = RAIZ_REDTURING / "targets.yaml"

if str(RAIZ_REDTURING) not in sys.path:
    sys.path.insert(0, str(RAIZ_REDTURING))

TIPOS = ("http", "agente", "guardrail", "simulado")
NOMBRE_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_-]{1,48}$")

CABECERA = """# Objetivos atacables por Red Turing y DeepTeam.
#
# Este archivo lo administra el dashboard de seguridad (sección Objetivos); si
# lo editas a mano, ten en cuenta que al guardar desde el dashboard se reescribe
# y los comentarios se pierden. Está en .gitignore porque contiene rutas locales
# y nombres de variables de entorno.
#
# Tipos: http (agente desplegado tras una URL), agente (Python importable),
# guardrail (solo el filtro de entrada), simulado (de mentira, para probar el arnés).
# Los tokens nunca van aquí: `env_token` es el NOMBRE de la variable de entorno.

"""

CAMPOS_POR_TIPO: Dict[str, List[str]] = {
    "http": ["url", "metodo", "cuerpo", "ruta_respuesta", "codigos_bloqueo", "env_token", "plantilla_auth", "cabeceras"],
    "agente": ["ruta_proyecto", "modulo", "funcion", "param_sesion", "formato_sesion", "prefijo_sesion", "guardrail"],
    "guardrail": ["ruta_proyecto", "modulo", "funcion"],
    "simulado": ["modo"],
}
CAMPOS_COMUNES = ["tipo", "descripcion", "proposito"]

PLANTILLA_HTTP = {
    "url": "https://tu-api.example.com/chat",
    "metodo": "POST",
    "cuerpo": {"mensaje": "{payload}", "session_id": "{session_id}"},
    "ruta_respuesta": "respuesta",
    "codigos_bloqueo": [403, 422],
    "env_token": "",
    "plantilla_auth": "Bearer {token}",
    "cabeceras": {},
}


def leer_todos() -> Dict[str, Dict[str, Any]]:
    if not RUTA_TARGETS.is_file():
        return {}
    datos = yaml.safe_load(RUTA_TARGETS.read_text(encoding="utf-8")) or {}
    return dict(datos.get("targets", {}) or {})


def _guardar_todos(objetivos: Dict[str, Dict[str, Any]]) -> None:
    cuerpo = yaml.safe_dump({"targets": objetivos}, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100)
    RUTA_TARGETS.write_text(CABECERA + cuerpo, encoding="utf-8")


def _publico(nombre: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Vista para el frontend. No hay secretos en el YAML, pero se filtra igual por si acaso."""
    tipo = str(cfg.get("tipo", "?"))
    salida: Dict[str, Any] = {
        "nombre": nombre,
        "tipo": tipo,
        "descripcion": cfg.get("descripcion", ""),
        "proposito": cfg.get("proposito", ""),
        "con_coste": tipo in ("agente", "http"),
        "sirve_para_deepteam": tipo in ("agente", "http", "simulado"),
        "destino": cfg.get("url") or cfg.get("ruta_proyecto") or cfg.get("modo", ""),
        "config": {k: v for k, v in cfg.items() if k in CAMPOS_POR_TIPO.get(tipo, []) and k not in ("cabeceras",)},
    }
    if tipo == "http":
        cab = dict(cfg.get("cabeceras", {}) or {})
        salida["config"]["cabeceras"] = {k: ("••••" if k.lower() in ("authorization", "x-api-key", "api-key") else v) for k, v in cab.items()}
        salida["config"]["token_en_entorno"] = bool(cfg.get("env_token")) and bool(__import__("os").getenv(str(cfg.get("env_token"))))
    if tipo == "agente":
        g = cfg.get("guardrail")
        salida["permite_solo_llm"] = bool(g)  # sin guardrail declarado no sabemos qué neutralizar
    return salida


def listar() -> List[Dict[str, Any]]:
    return [_publico(n, c) for n, c in sorted(leer_todos().items())]


def obtener(nombre: str) -> Optional[Dict[str, Any]]:
    cfg = leer_todos().get(nombre)
    return _publico(nombre, cfg) if cfg else None


def _validar(nombre: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not NOMBRE_VALIDO.match(nombre):
        raise ValueError("Nombre inválido: minúsculas, dígitos, guiones y guion bajo; 2 a 49 caracteres.")
    tipo = str(cfg.get("tipo", "")).strip()
    if tipo not in TIPOS:
        raise ValueError(f"Tipo '{tipo}' desconocido. Usa uno de {TIPOS}.")
    limpio: Dict[str, Any] = {"tipo": tipo}
    for k in ("descripcion", "proposito"):
        if cfg.get(k):
            limpio[k] = str(cfg[k]).strip()

    if tipo == "http":
        url = str(cfg.get("url", "")).strip()
        if not re.match(r"^https?://", url):
            raise ValueError("La URL debe empezar por http:// o https://.")
        limpio["url"] = url
        limpio["metodo"] = str(cfg.get("metodo", "POST")).upper() or "POST"
        cuerpo = cfg.get("cuerpo", PLANTILLA_HTTP["cuerpo"])
        if isinstance(cuerpo, str):
            try:
                cuerpo = json.loads(cuerpo)
            except ValueError:
                raise ValueError("El cuerpo debe ser JSON válido.") from None
        if not isinstance(cuerpo, dict) or "{payload}" not in json.dumps(cuerpo):
            raise ValueError("El cuerpo debe ser un objeto JSON que contenga el marcador {payload}.")
        limpio["cuerpo"] = cuerpo
        limpio["ruta_respuesta"] = str(cfg.get("ruta_respuesta", "respuesta")).strip() or "respuesta"
        codigos = cfg.get("codigos_bloqueo", [403])
        if isinstance(codigos, str):
            codigos = [int(x) for x in re.split(r"[,\s]+", codigos) if x.strip()]
        limpio["codigos_bloqueo"] = [int(c) for c in codigos]
        if cfg.get("env_token"):
            env = str(cfg["env_token"]).strip()
            if not re.match(r"^[A-Z][A-Z0-9_]*$", env):
                raise ValueError("env_token debe ser el NOMBRE de una variable de entorno (MAYÚSCULAS), no el token.")
            limpio["env_token"] = env
            limpio["plantilla_auth"] = str(cfg.get("plantilla_auth") or "Bearer {token}")
        cab = cfg.get("cabeceras") or {}
        if isinstance(cab, str):
            try:
                cab = json.loads(cab) if cab.strip() else {}
            except ValueError:
                raise ValueError("Las cabeceras deben ser un objeto JSON.") from None
        if cab:
            limpio["cabeceras"] = {str(k): str(v) for k, v in dict(cab).items()}

    elif tipo in ("agente", "guardrail"):
        ruta = str(cfg.get("ruta_proyecto", "")).strip()
        if not ruta:
            raise ValueError("Falta ruta_proyecto (carpeta del proyecto Python).")
        limpio["ruta_proyecto"] = ruta
        limpio["modulo"] = str(cfg.get("modulo") or ("agente_sec_langfuse" if tipo == "agente" else "guardrails.input_guardrail")).strip()
        limpio["funcion"] = str(cfg.get("funcion") or ("chat_con_agente" if tipo == "agente" else "verificar_input_guardrail")).strip()
        if tipo == "agente":
            if cfg.get("param_sesion") is not None and str(cfg.get("param_sesion")).strip() != "":
                limpio["param_sesion"] = str(cfg["param_sesion"]).strip()
            limpio["formato_sesion"] = str(cfg.get("formato_sesion") or "uuid")
            g = cfg.get("guardrail")
            if isinstance(g, str):
                g = json.loads(g) if g.strip() else None
            if g:
                limpio["guardrail"] = {
                    "modulo": str(g.get("modulo") or "guardrails.input_guardrail"),
                    "funcion": str(g.get("funcion") or "verificar_input_guardrail"),
                    "evaluar_llm_siempre": bool(g.get("evaluar_llm_siempre", False)),
                }
                if g.get("nombre_en_agente"):
                    limpio["guardrail"]["nombre_en_agente"] = str(g["nombre_en_agente"])
    else:
        modo = str(cfg.get("modo", "realista"))
        if modo not in ("vulnerable", "blindado", "realista"):
            raise ValueError("modo debe ser vulnerable, blindado o realista.")
        limpio["modo"] = modo
    return limpio


def guardar(nombre: str, cfg: Dict[str, Any], renombrar_desde: Optional[str] = None) -> Dict[str, Any]:
    todos = leer_todos()
    limpio = _validar(nombre, cfg)
    if renombrar_desde and renombrar_desde != nombre:
        todos.pop(renombrar_desde, None)
    todos[nombre] = limpio
    _guardar_todos(todos)
    return _publico(nombre, limpio)


def eliminar(nombre: str) -> bool:
    todos = leer_todos()
    if nombre not in todos:
        return False
    del todos[nombre]
    _guardar_todos(todos)
    return True


def probar(nombre: str, mensaje: str = "Hola, ¿qué trámites puedo consultar contigo?") -> Dict[str, Any]:
    """
    Envía un mensaje inocuo y devuelve lo que pasó. Para un objetivo `agente`
    importa el proyecto real (puede tardar la primera vez); para `http` hace
    la petición tal cual la haría una corrida.
    """
    from redturing.targets import construir_objetivo

    inicio = time.perf_counter()
    try:
        objetivo = construir_objetivo(nombre)
    except Exception as e:  # noqa: BLE001 — queremos mostrar el error tal cual al usuario
        return {"ok": False, "fase": "construccion", "error": f"{type(e).__name__}: {e}", "latencia_ms": round((time.perf_counter() - inicio) * 1000)}
    r = objetivo.enviar(mensaje)
    return {
        "ok": r.error is None,
        "fase": "envio",
        "tipo": objetivo.tipo,
        "bloqueado": r.bloqueado,
        "capa": r.capa,
        "motivo": r.motivo,
        "texto": (r.texto or "")[:1200],
        "error": r.error,
        "latencia_ms": round(r.latencia_ms),
        "crudo": {k: v for k, v in (r.crudo or {}).items() if k in ("status", "guardrail")},
    }
