"""
Backend del dashboard de seguridad: Red Turing y DeepTeam bajo una sola API.

Red Turing se reutiliza tal cual (mismo paquete, misma carpeta reports/, mismo
lanzador con SSE). DeepTeam se envuelve con `deepteam_runner`, que añade la
elección de modelo adversario y juez. El frontend React compilado se sirve desde
`frontend/dist` cuando existe; en desarrollo Vite hace proxy a /api.

Ejecutar (con el intérprete conda del agente, que tiene LangChain y DeepTeam):
    /opt/anaconda3/envs/DP-LangChain-Seguridad/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8740

Solo escucha en localhost y rechaza cualquier petición cuyo Host u Origin no
sean locales, por las mismas razones que el dashboard original: los informes
contienen los payloads que atravesaron tus defensas y las respuestas del agente.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

RAIZ_MODULO = Path(__file__).resolve().parent.parent.parent
RAIZ_REDTURING = RAIZ_MODULO / "Red-Turing"
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Credenciales del propio dashboard: la clave de OpenAI para el adversario y el
# juez de DeepTeam (y el juez opcional de Red Turing), y los tokens de los
# objetivos HTTP (RT_TOKEN_*). Van en backend/.env, nunca en el código ni en
# targets.yaml. Como respaldo, si existe el .env del proyecto TramiBot se toma
# de ahí lo que falte. Debe cargarse ANTES de importar Red Turing, cuyo juez lee
# la clave al importarse.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(RAIZ_MODULO / "LangChain-AgenteIA-MultiTool-Seguridad" / ".env", override=False)

if str(RAIZ_REDTURING) not in sys.path:
    sys.path.insert(0, str(RAIZ_REDTURING))

from redturing.dashboard.lanzador import (  # noqa: E402
    CorridaEnCurso,
    Lanzador,
    RequiereConfirmacion,
    estado_juez,
    listar_objetivos,
    listar_suites,
    planificar,
)
from redturing.dashboard.server import (  # noqa: E402
    DIRECTORIO_INFORMES,
    _leer,
    _resolver,
    comparar_archivos,
    listar_corridas,
    origen_permitido,
)

import deepteam_runner as dt  # noqa: E402
import objetivos as reg  # noqa: E402

PUERTO = 8740
app = FastAPI(title="Dashboard de seguridad · Red Turing + DeepTeam", docs_url=None, redoc_url=None)

lanzador = Lanzador(DIRECTORIO_INFORMES)
runner = dt.RunnerDeepTeam(hay_otra_actividad=lambda: lanzador.activa)


# ────────────────────────── seguridad: solo localhost ──────────────────────────

@app.middleware("http")
async def solo_local(request: Request, call_next):
    host = request.headers.get("host")
    origen = request.headers.get("origin")
    # Vite en desarrollo vive en otro puerto local: se acepta cualquier puerto de localhost.
    def local(v: Optional[str]) -> bool:
        if not v:
            return True
        v = v.lower().replace("http://", "")
        nombre = v.split("/")[0].split(":")[0]
        return nombre in ("127.0.0.1", "localhost", "[::1]")

    if not host or not local(host) or not local(origen):
        return JSONResponse({"error": "petición rechazada: Host u Origin no son locales"}, status_code=403)
    return await call_next(request)


def _error(codigo: int, mensaje: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": mensaje, **extra}, status_code=codigo)


# ────────────────────────── Red Turing ──────────────────────────

@app.get("/api/redturing/corridas")
def rt_corridas():
    return listar_corridas(DIRECTORIO_INFORMES)


@app.get("/api/redturing/corrida")
def rt_corrida(archivo: str):
    ruta = _resolver(archivo, DIRECTORIO_INFORMES)
    if ruta is None:
        raise HTTPException(404, "informe no encontrado")
    return _leer(ruta)


@app.get("/api/redturing/comparar")
def rt_comparar(antes: str, despues: str):
    a, b = _resolver(antes, DIRECTORIO_INFORMES), _resolver(despues, DIRECTORIO_INFORMES)
    if a is None or b is None:
        raise HTTPException(404, "alguno de los informes no existe")
    return comparar_archivos(_leer(a), _leer(b))


@app.get("/api/redturing/objetivos")
def rt_objetivos():
    try:
        return listar_objetivos()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/redturing/suites")
def rt_suites():
    return listar_suites()


@app.get("/api/redturing/juez")
def rt_juez():
    return estado_juez()


@app.get("/api/redturing/plan")
def rt_plan(request: Request):
    q = request.query_params
    peticion = {
        "objetivo": q.get("objetivo", ""),
        "suites": q.get("suites") or None,
        "categorias": q.get("categorias") or None,
        "severidad": q.get("severidad") or None,
        "limite": q.get("limite") or None,
        "workers": q.get("workers") or None,
        "usar_juez": q.get("usar_juez") not in ("0", "false", "no"),
    }
    try:
        return planificar(peticion)
    except (FileNotFoundError, KeyError, ValueError) as e:
        raise HTTPException(400, str(e).strip("'\""))


@app.get("/api/redturing/corrida-activa")
def rt_activa():
    return lanzador.estado()


@app.post("/api/redturing/correr")
async def rt_correr(request: Request):
    cuerpo = await request.json()
    if runner.activa:
        return _error(409, "Hay una evaluación de DeepTeam en curso; las dos usan el mismo agente.")
    try:
        return JSONResponse(lanzador.lanzar(cuerpo), status_code=202)
    except CorridaEnCurso as e:
        return _error(409, str(e), corrida=lanzador.estado())
    except RequiereConfirmacion as e:
        return _error(428, str(e), requiere_confirmacion=True, tipo=e.tipo, casos=e.casos)
    except (FileNotFoundError, KeyError, ValueError) as e:
        return _error(400, str(e).strip("'\""))


@app.post("/api/redturing/cancelar")
def rt_cancelar():
    if lanzador.cancelar():
        return {"ok": True, "corrida": lanzador.estado()}
    return _error(409, "no hay ninguna corrida en curso")


@app.get("/api/redturing/eventos")
def rt_eventos(id: str, desde: int = 0, request: Request = None):
    ultimo = request.headers.get("last-event-id") if request else None
    if ultimo is not None:
        try:
            desde = int(ultimo) + 1
        except ValueError:
            pass
    try:
        flujo = lanzador.eventos(id, desde)
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\""))

    def generar():
        for ev in flujo:
            if ev is None:
                yield ": latido\n\n"
            else:
                yield f"id: {ev['n']}\nevent: {ev['tipo']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(generar(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ────────────────────────── Objetivos (compartidos) ──────────────────────────

@app.get("/api/objetivos")
def obj_listar():
    return reg.listar()


@app.get("/api/objetivos/plantilla-http")
def obj_plantilla():
    return reg.PLANTILLA_HTTP


@app.post("/api/objetivos")
async def obj_guardar(request: Request):
    cuerpo = await request.json()
    if not isinstance(cuerpo, dict) or not cuerpo.get("nombre"):
        return _error(400, "falta el nombre del objetivo")
    if lanzador.activa or runner.activa:
        return _error(409, "hay una corrida o evaluación en curso; espera a que termine para editar objetivos")
    try:
        return reg.guardar(str(cuerpo["nombre"]).strip(), cuerpo.get("config") or {}, cuerpo.get("renombrar_desde"))
    except (ValueError, KeyError, TypeError) as e:
        return _error(400, str(e).strip("'\""))


@app.delete("/api/objetivos/{nombre}")
def obj_eliminar(nombre: str):
    if lanzador.activa or runner.activa:
        return _error(409, "hay una corrida o evaluación en curso")
    if not reg.eliminar(nombre):
        return _error(404, "objetivo no encontrado")
    return {"ok": True}


@app.post("/api/objetivos/{nombre}/probar")
async def obj_probar(nombre: str, request: Request):
    if lanzador.activa or runner.activa:
        return _error(409, "hay una corrida o evaluación en curso; las dos usan el agente")
    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001
        cuerpo = {}
    mensaje = str((cuerpo or {}).get("mensaje") or "Hola, ¿qué trámites puedo consultar contigo?")
    import asyncio
    return await asyncio.to_thread(reg.probar, nombre, mensaje)


# ────────────────────────── DeepTeam ──────────────────────────

@app.get("/api/deepteam/catalogo")
def dt_catalogo():
    return dt.catalogo()


@app.get("/api/deepteam/config")
def dt_config():
    return dt.leer_config()


@app.get("/api/entorno")
def entorno():
    """Qué credenciales están presentes (solo sí/no, nunca valores)."""
    import os
    return {
        "openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
        "tokens_objetivos": sorted(k for k in os.environ if k.startswith("RT_TOKEN_")),
        "archivo_env": str((Path(__file__).resolve().parent / ".env").exists()),
    }


@app.put("/api/deepteam/config")
async def dt_config_guardar(request: Request):
    cuerpo = await request.json()
    if not isinstance(cuerpo, dict):
        return _error(400, "se espera un objeto JSON")
    return dt.guardar_config(cuerpo)


@app.get("/api/deepteam/evaluaciones")
def dt_evaluaciones():
    return dt.listar_evaluaciones()


@app.get("/api/deepteam/evaluacion")
def dt_evaluacion(archivo: str):
    d = dt.leer_evaluacion(archivo)
    if d is None:
        raise HTTPException(404, "evaluación no encontrada")
    return d


@app.get("/api/deepteam/estado")
def dt_estado():
    return runner.estado()


@app.post("/api/deepteam/estimar")
async def dt_estimar(request: Request):
    cuerpo = await request.json()
    try:
        p = runner.normalizar(cuerpo)
    except (ValueError, KeyError, TypeError) as e:
        return _error(400, str(e).strip("'\""))
    casos = runner.estimar(p)
    multi = sum(1 for a in p["ataques"] if a in ("CrescendoJailbreaking", "LinearJailbreaking", "TreeJailbreaking", "SequentialJailbreak", "BadLikertJudge"))
    return {
        "casos": casos,
        "llamadas_agente_min": casos,
        "llamadas_agente_max": casos * (5 if multi else 1),
        "llamadas_adversario_aprox": casos * (2 if p["en_espanol"] else 1) * 2,
        "llamadas_juez": casos,
        "modelo_adversario": p["modelo_adversario"],
        "modelo_juez": p["modelo_juez"],
        "incluye_multi_turno": multi > 0,
    }


@app.post("/api/deepteam/evaluar")
async def dt_evaluar(request: Request):
    cuerpo = await request.json()
    if not cuerpo.get("confirmar"):
        return _error(428, "Esta evaluación hace llamadas reales al adversario, al juez y a TramiBot. Confírmala.", requiere_confirmacion=True)
    try:
        return JSONResponse(runner.lanzar(cuerpo), status_code=202)
    except dt.EvaluacionEnCurso as e:
        return _error(409, str(e), evaluacion=runner.estado())
    except (ValueError, KeyError, TypeError) as e:
        return _error(400, str(e).strip("'\""))


# ────────────────────────── frontend compilado ──────────────────────────

if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{ruta:path}")
    def spa(ruta: str):
        candidato = DIST / ruta
        if ruta and candidato.is_file():
            return FileResponse(candidato)
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PUERTO)
