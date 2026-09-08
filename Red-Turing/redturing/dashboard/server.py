"""
Servidor HTTP del dashboard: lee los informes de `reports/` y lanza corridas.

Solo escucha en localhost. Los informes contienen los payloads que atravesaron
tus defensas y las respuestas literales del agente; no es algo para exponer en
la red. Los nombres de archivo que llegan por la URL se validan contra un patrón
estricto y se resuelven dentro de `reports/` — nunca se abre una ruta arbitraria.

Como ahora también LANZA corridas, hay dos defensas más:

- **Host y Origin se verifican en todas las peticiones.** Una página web
  maliciosa abierta en el mismo navegador podría intentar hablar con
  127.0.0.1:8731 (CSRF hacia localhost, o DNS rebinding). Se rechaza todo lo que
  no venga con Host local y, si trae Origin, Origin local.
- **Escribir exige JSON y una confirmación explícita** para los objetivos que
  cuestan dinero por caso. La confirmación la muestra el dashboard con la cifra
  de llamadas previstas; el servidor no la da por supuesta.

Rutas de lectura:
    GET  /api/corridas                 índice de informes
    GET  /api/corrida?archivo=         un informe completo
    GET  /api/comparar?antes=&despues= diferencia caso a caso
    GET  /api/objetivos                targets.yaml, sin credenciales
    GET  /api/suites                   suites y número de casos
    GET  /api/juez                     si el juez LLM podría actuar
    GET  /api/plan?…                   qué lanzaría una petición (sin lanzarla)
    GET  /api/corrida-activa           estado de la corrida viva o de la última
    GET  /api/eventos?id=&desde=       flujo SSE con el progreso caso a caso

Rutas de escritura (POST, JSON):
    POST /api/correr                   arranca una corrida (409 si hay una activa,
                                       428 si falta la confirmación)
    POST /api/cancelar                 cancelación cooperativa
"""

from __future__ import annotations

import json
import re
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from .lanzador import (
    CorridaEnCurso,
    Lanzador,
    RequiereConfirmacion,
    estado_juez,
    listar_objetivos,
    listar_suites,
    planificar,
)

RAIZ = Path(__file__).resolve().parent.parent.parent
DIRECTORIO_INFORMES = RAIZ / "reports"
PAGINA = Path(__file__).resolve().parent / "index.html"

PUERTO_POR_DEFECTO = 8731
HOST = "127.0.0.1"
HOSTS_LOCALES = frozenset({"127.0.0.1", "localhost", "[::1]"})
CUERPO_MAXIMO = 64 * 1024  # un POST legítimo pesa unos cientos de bytes

# Un informe válido se llama redturing-<objetivo>-<marca>.json (o cualquier nombre
# en baseline/). Cualquier otra cosa en la URL se rechaza antes de tocar el disco.
_NOMBRE_VALIDO = re.compile(r"^(baseline/)?[A-Za-z0-9._-]+\.json$")


def _leer(ruta: Path) -> Dict[str, Any]:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _resolver(nombre: str, directorio: Path = DIRECTORIO_INFORMES) -> Optional[Path]:
    """Convierte un nombre recibido por URL en una ruta segura dentro de reports/."""
    if not _NOMBRE_VALIDO.match(nombre):
        return None
    ruta = (directorio / nombre).resolve()
    if directorio.resolve() not in ruta.parents or not ruta.is_file():
        return None
    return ruta


def origen_permitido(host: Optional[str], origen: Optional[str], puerto: int) -> bool:
    """
    ¿La petición viene del propio navegador del usuario hablando con localhost?

    `host` debe ser un nombre local con el puerto del servidor (o sin puerto). Si
    hay cabecera `Origin` —la ponen los navegadores en POST y en peticiones
    cross-site— debe apuntar también a localhost en ese puerto. Una web ajena
    abierta en otra pestaña tendrá su propio Origin y se rechaza aquí.
    """

    def local(valor: str) -> bool:
        valor = valor.strip().lower()
        if valor.startswith("http://"):
            valor = valor[len("http://") :]
        elif "://" in valor:
            return False  # https u otro esquema hacia localhost no es este servidor
        if valor.startswith("["):  # IPv6 entre corchetes
            nombre, _, resto = valor.partition("]")
            nombre += "]"
            puerto_txt = resto[1:] if resto.startswith(":") else ""
        else:
            nombre, _, puerto_txt = valor.partition(":")
        if nombre not in HOSTS_LOCALES:
            return False
        return puerto_txt in ("", str(puerto))

    if not host or not local(host):
        return False
    if origen and origen.lower() != "null" and not local(origen):
        return False
    return True


def _resumen(ruta: Path, directorio: Path) -> Dict[str, Any]:
    datos = _leer(ruta)
    resumen = datos.get("resumen", {})
    evaluados = resumen.get("evaluados", resumen.get("total", 0) - resumen.get("errores", 0))
    controles = datos.get("asr_por_categoria", {}).get("control_falsos_positivos", {})
    return {
        "archivo": ruta.relative_to(directorio).as_posix(),
        "es_baseline": ruta.parent.name == "baseline",
        "objetivo": datos.get("objetivo", "?"),
        "tipo_objetivo": datos.get("tipo_objetivo", "?"),
        "inicio": datos.get("inicio", ""),
        "duracion_s": datos.get("duracion_s", 0),
        "juez_activo": datos.get("juez_activo", False),
        "total": resumen.get("total", 0),
        "evaluados": evaluados,
        "exitosos": resumen.get("exitosos", 0),
        "errores": resumen.get("errores", 0),
        "asr": resumen.get("asr", 0.0),
        "falsos_positivos": controles.get("asr"),
    }


def listar_corridas(directorio: Path = DIRECTORIO_INFORMES) -> List[Dict[str, Any]]:
    """Resumen de cada informe en reports/ y reports/baseline/, más reciente primero."""
    rutas = list(directorio.glob("*.json")) + list((directorio / "baseline").glob("*.json"))
    corridas = []
    for ruta in rutas:
        try:
            corridas.append(_resumen(ruta, directorio))
        except (ValueError, KeyError, OSError):
            continue  # un JSON corrupto no debe tumbar el índice entero
    corridas.sort(key=lambda c: c["inicio"], reverse=True)
    return corridas


def comparar_archivos(antes: Dict[str, Any], despues: Dict[str, Any]) -> Dict[str, Any]:
    """
    Diferencia caso a caso entre dos informes ya cargados.

    Regresión y corrección exigen que el caso se haya evaluado en AMBAS corridas.
    Un caso que antes falló por servicio caído y ahora penetra no es una
    regresión: es su primera medición, y va en su propio cubo para no inflar
    ni el conteo de regresiones ni el de "casos nuevos".
    """

    def por_id(datos: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {r["caso"]["id"]: r for r in datos.get("resultados", [])}

    def medido(r: Dict[str, Any]) -> bool:
        return not r.get("respuesta", {}).get("error")

    def exito(r: Dict[str, Any]) -> bool:
        return bool(r["veredicto"]["exito"])

    a, b = por_id(antes), por_id(despues)
    comunes = sorted(set(a) & set(b))
    ambos = [i for i in comunes if medido(a[i]) and medido(b[i])]

    def ficha(id_: str, fuente: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        r = fuente[id_]
        return {
            "id": id_,
            "categoria": r["caso"]["categoria"],
            "severidad": r["caso"]["severidad"],
            "exito": exito(r),
            "evidencia": r["veredicto"].get("evidencia", ""),
        }

    return {
        "regresiones": [ficha(i, b) for i in ambos if exito(b[i]) and not exito(a[i])],
        "corregidos": [ficha(i, b) for i in ambos if exito(a[i]) and not exito(b[i])],
        "casos_nuevos": [ficha(i, b) for i in sorted(set(b) - set(a))],
        "casos_retirados": [ficha(i, a) for i in sorted(set(a) - set(b))],
        "primera_medicion": [ficha(i, b) for i in comunes if not medido(a[i]) and medido(b[i])],
        "sin_medir_ahora": [ficha(i, a) for i in comunes if medido(a[i]) and not medido(b[i])],
        "asr_antes": antes.get("resumen", {}).get("asr", 0.0),
        "asr_despues": despues.get("resumen", {}).get("asr", 0.0),
    }


def _peticion_de_query(params: Dict[str, List[str]]) -> Dict[str, Any]:
    """Traduce la query de /api/plan al mismo dict que acepta POST /api/correr."""

    def uno(clave: str) -> str:
        return params.get(clave, [""])[0]

    return {
        "objetivo": uno("objetivo"),
        "suites": uno("suites") or None,
        "categorias": uno("categorias") or None,
        "severidad": uno("severidad") or None,
        "limite": uno("limite") or None,
        "workers": uno("workers") or None,
        "usar_juez": uno("usar_juez") not in ("0", "false", "no"),
    }


class _Manejador(BaseHTTPRequestHandler):
    directorio: Path = DIRECTORIO_INFORMES
    lanzador: Lanzador
    puerto: int = PUERTO_POR_DEFECTO

    def log_message(self, formato, *args):  # noqa: D102 — silencia el log por petición
        pass

    # ── utilidades de respuesta ──

    def _json(self, cuerpo: Any, estado: HTTPStatus = HTTPStatus.OK) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def _error(self, estado: HTTPStatus, mensaje: str, **extra: Any) -> None:
        self._json({"error": mensaje, **extra}, estado)

    def _origen_ok(self) -> bool:
        if origen_permitido(self.headers.get("Host"), self.headers.get("Origin"), self.puerto):
            return True
        self._error(HTTPStatus.FORBIDDEN, "petición rechazada: Host u Origin no son locales")
        return False

    def _leer_json(self) -> Optional[Dict[str, Any]]:
        tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if tipo != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "se espera Content-Type: application/json")
            return None
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            largo = -1
        if largo < 0 or largo > CUERPO_MAXIMO:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "cuerpo demasiado grande")
            return None
        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "JSON mal formado")
            return None
        if not isinstance(cuerpo, dict):
            self._error(HTTPStatus.BAD_REQUEST, "se espera un objeto JSON")
            return None
        return cuerpo

    # ── GET ──

    def do_GET(self) -> None:  # noqa: N802 — nombre fijado por BaseHTTPRequestHandler
        if not self._origen_ok():
            return
        url = urlparse(self.path)
        params = parse_qs(url.query)

        if url.path in ("/", "/index.html"):
            cuerpo = PAGINA.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)
            return

        if url.path == "/api/corridas":
            self._json(listar_corridas(self.directorio))
            return

        if url.path == "/api/corrida":
            ruta = _resolver(params.get("archivo", [""])[0], self.directorio)
            if ruta is None:
                self._error(HTTPStatus.NOT_FOUND, "informe no encontrado")
                return
            self._json(_leer(ruta))
            return

        if url.path == "/api/comparar":
            ruta_a = _resolver(params.get("antes", [""])[0], self.directorio)
            ruta_b = _resolver(params.get("despues", [""])[0], self.directorio)
            if ruta_a is None or ruta_b is None:
                self._error(HTTPStatus.NOT_FOUND, "alguno de los informes no existe")
                return
            self._json(comparar_archivos(_leer(ruta_a), _leer(ruta_b)))
            return

        if url.path == "/api/objetivos":
            try:
                self._json(listar_objetivos())
            except FileNotFoundError as e:
                self._error(HTTPStatus.NOT_FOUND, str(e))
            return

        if url.path == "/api/suites":
            try:
                self._json(listar_suites())
            except (FileNotFoundError, ValueError) as e:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
            return

        if url.path == "/api/juez":
            self._json(estado_juez())
            return

        if url.path == "/api/plan":
            try:
                self._json(planificar(_peticion_de_query(params)))
            except (FileNotFoundError, KeyError, ValueError) as e:
                self._error(HTTPStatus.BAD_REQUEST, str(e).strip("'\""))
            return

        if url.path == "/api/corrida-activa":
            self._json(self.lanzador.estado())
            return

        if url.path == "/api/eventos":
            self._eventos(params.get("id", [""])[0], params.get("desde", ["0"])[0])
            return

        self._error(HTTPStatus.NOT_FOUND, "ruta desconocida")

    def _eventos(self, id_corrida: str, desde_txt: str) -> None:
        """Server-Sent Events: rehace el historial y luego sigue en vivo hasta el final."""
        try:
            desde = max(0, int(desde_txt or 0))
        except ValueError:
            desde = 0
        # Si el navegador se reconectó solo, EventSource manda el último id que
        # recibió: seguimos desde el siguiente en lugar de repetir el historial.
        ultimo = self.headers.get("Last-Event-ID")
        if ultimo is not None:
            try:
                desde = int(ultimo) + 1
            except ValueError:
                pass
        try:
            flujo = self.lanzador.eventos(id_corrida, desde)
        except KeyError as e:
            self._error(HTTPStatus.NOT_FOUND, str(e).strip("'\""))
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            for ev in flujo:
                if ev is None:
                    self.wfile.write(b": latido\n\n")
                else:
                    linea = json.dumps(ev, ensure_ascii=False)
                    self.wfile.write(
                        f"id: {ev['n']}\nevent: {ev['tipo']}\ndata: {linea}\n\n".encode("utf-8")
                    )
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return  # el navegador cerró la pestaña: no hay nada que limpiar

    # ── POST ──

    def do_POST(self) -> None:  # noqa: N802
        if not self._origen_ok():
            return
        url = urlparse(self.path)

        if url.path == "/api/correr":
            cuerpo = self._leer_json()
            if cuerpo is None:
                return
            try:
                self._json(self.lanzador.lanzar(cuerpo), HTTPStatus.ACCEPTED)
            except CorridaEnCurso as e:
                self._error(HTTPStatus.CONFLICT, str(e), corrida=self.lanzador.estado())
            except RequiereConfirmacion as e:
                self._error(
                    HTTPStatus.PRECONDITION_REQUIRED, str(e),
                    requiere_confirmacion=True, tipo=e.tipo, casos=e.casos,
                )
            except (FileNotFoundError, KeyError, ValueError) as e:
                self._error(HTTPStatus.BAD_REQUEST, str(e).strip("'\""))
            return

        if url.path == "/api/cancelar":
            if self.lanzador.cancelar():
                self._json({"ok": True, "corrida": self.lanzador.estado()})
            else:
                self._error(HTTPStatus.CONFLICT, "no hay ninguna corrida en curso")
            return

        self._error(HTTPStatus.NOT_FOUND, "ruta desconocida")


def servir(
    puerto: int = PUERTO_POR_DEFECTO,
    abrir: bool = True,
    directorio: Path = DIRECTORIO_INFORMES,
) -> None:
    """Arranca el servidor en localhost y bloquea hasta Ctrl+C."""
    directorio.mkdir(parents=True, exist_ok=True)
    _Manejador.directorio = directorio
    _Manejador.puerto = puerto
    _Manejador.lanzador = Lanzador(directorio)
    servidor = ThreadingHTTPServer((HOST, puerto), _Manejador)
    servidor.daemon_threads = True
    url = f"http://{HOST}:{puerto}/"

    print(f"\n  Red Turing · dashboard en {url}")
    print(f"  Leyendo informes de {directorio}")
    print("  Desde aquí también puedes lanzar corridas; las que cuestan piden confirmación.")
    print("  Ctrl+C para detener.\n")

    if abrir:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        if _Manejador.lanzador.activa:
            print("\n  Cancelando la corrida en curso…")
            _Manejador.lanzador.cancelar()
            _Manejador.lanzador.esperar(timeout=30)
        print("\n  Dashboard detenido.")
    finally:
        servidor.server_close()
