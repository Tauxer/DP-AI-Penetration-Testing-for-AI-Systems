"""
Lanzador de corridas para el dashboard: una a la vez, en un hilo, con eventos en vivo.

Es la pieza que permite disparar un ataque desde el navegador sin perder las
garantías que antes daba el CLI:

- **Una sola corrida activa.** Un segundo intento mientras hay una en curso se
  rechaza con `CorridaEnCurso`. Nunca hay dos hilos atacando al mismo agente.
- **Confirmación explícita para lo que cuesta dinero.** Los objetivos `agente` y
  `http` hacen una llamada real por caso; la petición debe traer `confirmar=True`
  o se rechaza con `RequiereConfirmacion` junto al número de llamadas previsto.
  El dashboard la pide al usuario mostrándole esa cifra.
- **Cancelación cooperativa.** `cancelar()` levanta una bandera que el runner
  consulta antes de enviar cada payload; lo que ya salió termina, lo demás no se
  envía, y el informe parcial se guarda igual que uno completo.
- **Sin estado compartido con el CLI.** Reutiliza `cargar_suites`,
  `filtrar_casos`, `construir_objetivo`, `ejecutar_corrida` y los reportes: lo
  que lanza el dashboard es exactamente lo que habría lanzado el comando `correr`
  con los mismos parámetros.

Los eventos se acumulan en memoria por corrida para que un navegador que se
conecta tarde (o recarga la página) reciba el historial completo antes de los
eventos en vivo.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..detectors import CascadaDetectores
from ..loader import cargar_suites, filtrar_casos, listar_suites
from ..models import CasoAtaque, ResultadoAtaque
from ..report import guardar_html, guardar_json
from ..runner import WORKERS_POR_DEFECTO, ejecutar_corrida
from ..targets import construir_objetivo, leer_config

# Tipos de objetivo que cuestan dinero y tiempo por caso: exigen confirmación.
TIPOS_CON_COSTE = frozenset({"agente", "http"})

WORKERS_MAXIMO = 16
FASES_ACTIVAS = frozenset({"preparando", "corriendo"})
FASES_FINALES = frozenset({"terminada", "cancelada", "error"})


class CorridaEnCurso(RuntimeError):
    """Ya hay una corrida activa; hay que esperar a que termine o cancelarla."""


class RequiereConfirmacion(ValueError):
    """El objetivo cuesta dinero por caso y la petición no vino confirmada."""

    def __init__(self, tipo: str, casos: int):
        super().__init__(
            f"El objetivo es de tipo '{tipo}': hará {casos} llamadas reales. "
            f"Confirma la corrida para continuar."
        )
        self.tipo = tipo
        self.casos = casos


def _normalizar_peticion(peticion: Dict[str, Any]) -> Dict[str, Any]:
    """Valida y tipa los parámetros que llegan del navegador. Lanza ValueError si algo no cuadra."""
    objetivo = str(peticion.get("objetivo") or "").strip()
    if not objetivo:
        raise ValueError("Falta el objetivo.")

    suites = peticion.get("suites") or None
    if suites is not None:
        if isinstance(suites, str):
            suites = [s for s in suites.split(",") if s.strip()]
        if not isinstance(suites, list) or not all(isinstance(s, str) for s in suites):
            raise ValueError("'suites' debe ser una lista de nombres.")
        suites = [s.strip() for s in suites if s.strip()] or None

    categorias = peticion.get("categorias") or None
    if categorias is not None:
        if isinstance(categorias, str):
            categorias = [c for c in categorias.split(",") if c.strip()]
        if not isinstance(categorias, list):
            raise ValueError("'categorias' debe ser una lista.")
        categorias = [str(c).strip() for c in categorias if str(c).strip()] or None

    severidad = peticion.get("severidad") or None
    if severidad is not None:
        severidad = str(severidad).strip() or None

    def entero(nombre: str, minimo: int, maximo: Optional[int]) -> Optional[int]:
        valor = peticion.get(nombre)
        if valor in (None, "", 0):
            return None
        try:
            valor = int(valor)
        except (TypeError, ValueError):
            raise ValueError(f"'{nombre}' debe ser un entero.") from None
        if valor < minimo or (maximo is not None and valor > maximo):
            tope = f" y {maximo}" if maximo is not None else ""
            raise ValueError(f"'{nombre}' debe estar entre {minimo}{tope}.")
        return valor

    return {
        "objetivo": objetivo,
        "suites": suites,
        "categorias": categorias,
        "severidad": severidad,
        "limite": entero("limite", 1, None),
        "workers": entero("workers", 1, WORKERS_MAXIMO) or WORKERS_POR_DEFECTO,
        "usar_juez": bool(peticion.get("usar_juez", True)),
        "generar_html": bool(peticion.get("generar_html", True)),
        "confirmar": bool(peticion.get("confirmar", False)),
    }


def _conteo(casos: List[CasoAtaque], campo: str) -> Dict[str, int]:
    salida: Dict[str, int] = {}
    for c in casos:
        clave = getattr(c, campo)
        salida[clave] = salida.get(clave, 0) + 1
    return dict(sorted(salida.items()))


def estado_juez() -> Dict[str, Any]:
    """¿El juez LLM podría actuar en esta máquina? Sin llamadas de red."""
    cascada = CascadaDetectores(usar_juez=True, tipo_objetivo="")
    return {
        "disponible": cascada.juez_activo,
        "motivo": "" if cascada.juez_activo else cascada.motivo_juez_inactivo,
        "modelo": cascada.juez.modelo if cascada.juez else "",
    }


def listar_objetivos() -> List[Dict[str, Any]]:
    """Objetivos de targets.yaml con lo que la UI necesita: tipo, destino y si cuesta."""
    try:
        objetivos = leer_config()
    except FileNotFoundError as e:
        raise FileNotFoundError(str(e)) from e
    salida = []
    for nombre, config in sorted(objetivos.items()):
        tipo = str(config.get("tipo", "?"))
        salida.append({
            "nombre": nombre,
            "tipo": tipo,
            "destino": config.get("ruta_proyecto") or config.get("url") or config.get("modo", ""),
            "con_coste": tipo in TIPOS_CON_COSTE,
        })
    return salida


def planificar(peticion: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula qué lanzaría una petición SIN construir el objetivo ni enviar nada.

    Es lo que el formulario consulta en cada cambio para mostrar «N casos, de los
    cuales M son controles» y, si el objetivo cuesta, «N llamadas reales».
    """
    p = _normalizar_peticion(peticion)
    objetivos = leer_config()
    if p["objetivo"] not in objetivos:
        raise KeyError(f"Objetivo '{p['objetivo']}' no declarado en targets.yaml.")
    tipo = str(objetivos[p["objetivo"]].get("tipo", "?"))

    casos = filtrar_casos(
        cargar_suites(p["suites"]),
        severidad=p["severidad"],
        categorias=p["categorias"],
        limite=p["limite"],
    )
    return {
        "objetivo": p["objetivo"],
        "tipo": tipo,
        "con_coste": tipo in TIPOS_CON_COSTE,
        "total": len(casos),
        "benignos": sum(1 for c in casos if c.benigno),
        "por_categoria": _conteo(casos, "categoria"),
        "por_severidad": _conteo(casos, "severidad"),
        "por_suite": _conteo(casos, "archivo_origen"),
        "workers": p["workers"],
        "usar_juez": p["usar_juez"],
    }


class _Corrida:
    """Estado mutable de una corrida y su cola de eventos para los suscriptores."""

    def __init__(self, peticion: Dict[str, Any], total: int, tipo: str):
        self.id = uuid.uuid4().hex[:12]
        self.peticion = peticion
        self.tipo = tipo
        self.fase = "preparando"
        self.inicio = datetime.now().isoformat(timespec="seconds")
        self.total = total
        self.completados = 0
        self.penetraron = 0
        self.contenidos = 0
        self.errores = 0
        self.archivo: Optional[str] = None
        self.archivo_html: Optional[str] = None
        self.mensaje: str = ""
        self.cancelar = threading.Event()
        self.eventos: List[Dict[str, Any]] = []
        self.cond = threading.Condition()

    @property
    def evaluados(self) -> int:
        return self.completados - self.errores

    @property
    def asr_parcial(self) -> float:
        return self.penetraron / self.evaluados if self.evaluados else 0.0

    def emitir(self, tipo: str, datos: Dict[str, Any], fase: Optional[str] = None) -> None:
        """Publica un evento y, si se indica, cambia de fase en la misma operación atómica."""
        with self.cond:
            if fase is not None:
                self.fase = fase
            self.eventos.append({**datos, "tipo": tipo, "n": len(self.eventos)})
            self.cond.notify_all()

    def resumen(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "fase": self.fase,
            "activa": self.fase in FASES_ACTIVAS,
            "objetivo": self.peticion["objetivo"],
            "tipo": self.tipo,
            "inicio": self.inicio,
            "total": self.total,
            "completados": self.completados,
            "penetraron": self.penetraron,
            "contenidos": self.contenidos,
            "errores": self.errores,
            "asr_parcial": round(self.asr_parcial, 4),
            "cancelacion_pedida": self.cancelar.is_set(),
            "archivo": self.archivo,
            "archivo_html": self.archivo_html,
            "mensaje": self.mensaje,
            "peticion": {k: v for k, v in self.peticion.items() if k != "confirmar"},
            "eventos": len(self.eventos),
        }


class Lanzador:
    """Orquesta como mucho una corrida viva y conserva la última para consultarla."""

    def __init__(self, directorio_informes: Path):
        self.directorio = directorio_informes
        self._lock = threading.Lock()
        self._corrida: Optional[_Corrida] = None
        self._hilo: Optional[threading.Thread] = None

    # ── consulta ──

    @property
    def activa(self) -> bool:
        return bool(self._corrida and self._corrida.fase in FASES_ACTIVAS)

    def estado(self) -> Optional[Dict[str, Any]]:
        """La corrida activa, o la última que hubo en este proceso. None si nunca hubo."""
        return self._corrida.resumen() if self._corrida else None

    def eventos(self, id_corrida: str, desde: int = 0, espera_s: float = 15.0) -> Iterator[Optional[Dict[str, Any]]]:
        """
        Itera los eventos de una corrida desde el índice `desde`, bloqueando
        hasta que lleguen nuevos. Rinde None cada `espera_s` sin novedades para
        que el servidor mande un latido y el navegador no cierre la conexión.
        Termina tras el evento final de la corrida.
        """
        corrida = self._corrida
        if corrida is None or corrida.id != id_corrida:
            raise KeyError("Esa corrida ya no está en memoria.")
        i = desde
        while True:
            with corrida.cond:
                while i >= len(corrida.eventos):
                    if corrida.fase in FASES_FINALES:
                        return
                    if not corrida.cond.wait(timeout=espera_s):
                        break
                pendientes = corrida.eventos[i:]
            if not pendientes:
                yield None
                continue
            for ev in pendientes:
                yield ev
                i += 1
                if ev["tipo"] in ("fin", "fallo"):
                    return

    # ── acciones ──

    def lanzar(self, peticion_cruda: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida, planifica y arranca la corrida en segundo plano. Devuelve el
        resumen inicial. Lanza CorridaEnCurso, RequiereConfirmacion, ValueError
        o KeyError; ninguna de ellas deja una corrida a medias.
        """
        with self._lock:
            if self.activa:
                raise CorridaEnCurso("Ya hay una corrida en curso.")

            plan = planificar(peticion_cruda)
            p = _normalizar_peticion(peticion_cruda)
            if plan["total"] == 0:
                raise ValueError("Ningún caso coincide con los filtros indicados.")
            if plan["con_coste"] and not p["confirmar"]:
                raise RequiereConfirmacion(plan["tipo"], plan["total"])

            corrida = _Corrida(p, plan["total"], plan["tipo"])
            self._corrida = corrida
            self._hilo = threading.Thread(
                target=self._ejecutar, args=(corrida,), name=f"redturing-{corrida.id}", daemon=True
            )
            self._hilo.start()
            return corrida.resumen()

    def cancelar(self) -> bool:
        """Pide parar la corrida activa. Devuelve False si no había ninguna."""
        corrida = self._corrida
        if corrida is None or corrida.fase not in FASES_ACTIVAS:
            return False
        corrida.cancelar.set()
        corrida.emitir("cancelando", {"mensaje": "Cancelación pedida: se omiten los casos que aún no salieron."})
        return True

    def esperar(self, timeout: Optional[float] = None) -> None:
        """Bloquea hasta que termine la corrida activa. Para tests y apagado ordenado."""
        if self._hilo:
            self._hilo.join(timeout)

    # ── ejecución en el hilo ──

    def _ejecutar(self, corrida: _Corrida) -> None:
        p = corrida.peticion
        try:
            casos = filtrar_casos(
                cargar_suites(p["suites"]),
                severidad=p["severidad"],
                categorias=p["categorias"],
                limite=p["limite"],
            )
            # Construir el objetivo puede tardar: importa el proyecto atacado y
            # carga sus dependencias. Por eso hay una fase 'preparando' visible.
            objetivo = construir_objetivo(p["objetivo"])
        except Exception as e:  # noqa: BLE001 — cualquier fallo de configuración es un error de la corrida
            corrida.mensaje = f"{type(e).__name__}: {e}"
            corrida.emitir("fallo", {"mensaje": corrida.mensaje}, fase="error")
            return

        cascada = CascadaDetectores(usar_juez=p["usar_juez"], tipo_objetivo=objetivo.tipo)
        corrida.emitir("inicio", {
            "objetivo": objetivo.nombre,
            "tipo_objetivo": objetivo.tipo,
            "total": len(casos),
            "workers": p["workers"],
            "juez_activo": cascada.juez_activo,
            "juez_motivo": "" if cascada.juez_activo else cascada.motivo_juez_inactivo,
        }, fase="corriendo")

        def al_terminar(resultado: ResultadoAtaque, i: int, total: int) -> None:
            corrida.completados += 1
            if resultado.respuesta.error:
                corrida.errores += 1
                estado = "err"
            elif resultado.veredicto.exito:
                corrida.penetraron += 1
                estado = "pen"
            else:
                corrida.contenidos += 1
                estado = "con"
            corrida.emitir("caso", {
                "i": i,
                "total": total,
                "id": resultado.caso.id,
                "categoria": resultado.caso.categoria,
                "tecnica": resultado.caso.tecnica,
                "severidad": resultado.caso.severidad,
                "benigno": resultado.caso.benigno,
                "resultado": estado,
                "nota": resultado.respuesta.capa or resultado.veredicto.detector,
                "evidencia": resultado.veredicto.evidencia,
                "bloqueado": resultado.respuesta.bloqueado,
                "texto": " ".join(resultado.respuesta.texto.split())[:240],
                "llm": None if resultado.veredicto_llm is None else (
                    "cedio" if resultado.veredicto_llm.exito
                    else ("revisar" if resultado.veredicto_llm.confianza == "baja" else "aguanto")
                ),
                "latencia_ms": round(resultado.respuesta.latencia_ms),
                "completados": corrida.completados,
                "penetraron": corrida.penetraron,
                "contenidos": corrida.contenidos,
                "errores": corrida.errores,
                "asr_parcial": round(corrida.asr_parcial, 4),
            })

        try:
            informe = ejecutar_corrida(
                objetivo=objetivo,
                casos=casos,
                usar_juez=p["usar_juez"],
                workers=p["workers"],
                al_terminar_caso=al_terminar,
                debe_parar=corrida.cancelar.is_set,
            )
        except Exception as e:  # noqa: BLE001 — el runner tolera objetivos caídos; esto es un fallo del propio arnés
            corrida.mensaje = f"{type(e).__name__}: {e}"
            corrida.emitir("fallo", {"mensaje": corrida.mensaje}, fase="error")
            return

        cancelada = corrida.cancelar.is_set()
        if informe.resultados:
            ruta_json = guardar_json(informe, self.directorio)
            corrida.archivo = ruta_json.relative_to(self.directorio).as_posix()
            if p["generar_html"]:
                ruta_html = guardar_html(informe, self.directorio)
                corrida.archivo_html = ruta_html.relative_to(self.directorio).as_posix()

        corrida.emitir("fin", {
            "cancelada": cancelada,
            "archivo": corrida.archivo,
            "archivo_html": corrida.archivo_html,
            "resumen": informe.a_dict()["resumen"],
            "duracion_s": round(informe.duracion_s, 2),
        }, fase="cancelada" if cancelada else "terminada")


__all__ = [
    "CorridaEnCurso",
    "Lanzador",
    "RequiereConfirmacion",
    "TIPOS_CON_COSTE",
    "estado_juez",
    "listar_objetivos",
    "listar_suites",
    "planificar",
]
