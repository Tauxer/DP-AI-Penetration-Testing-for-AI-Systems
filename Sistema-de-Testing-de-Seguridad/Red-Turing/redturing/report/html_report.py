"""
Informe HTML autocontenido, pensado para adjuntar o presentar.

Un solo archivo sin dependencias externas: se abre en cualquier navegador y se
manda por correo tal cual. Prioriza los ataques que penetraron, ordenados por
severidad; el resto queda en una tabla plegada.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from ..models import InformeCorrida

ORDEN_SEVERIDAD = {"critica": 0, "alta": 1, "media": 2, "baja": 3}

_ESTILOS = """
:root{color-scheme:light dark;--fondo:#fbfaf9;--panel:#fff;--texto:#1c1917;
--suave:#78716c;--borde:#e7e5e4;--rojo:#b91c1c;--verde:#15803d;--ambar:#b45309}
@media(prefers-color-scheme:dark){:root{--fondo:#1c1917;--panel:#292524;
--texto:#f5f5f4;--suave:#a8a29e;--borde:#44403c;--rojo:#f87171;--verde:#4ade80;--ambar:#fbbf24}}
*{box-sizing:border-box}body{margin:0;padding:2.5rem 1.5rem;background:var(--fondo);
color:var(--texto);font:15px/1.6 ui-sans-serif,-apple-system,Segoe UI,sans-serif}
.hoja{max-width:960px;margin:0 auto}h1{font-size:1.5rem;margin:0 0 .25rem}
h2{font-size:1rem;text-transform:uppercase;letter-spacing:.06em;color:var(--suave);
margin:2.5rem 0 .75rem;font-weight:600}.meta{color:var(--suave);font-size:.875rem;margin-bottom:2rem}
.asr{background:var(--panel);border:1px solid var(--borde);border-radius:10px;padding:1.5rem;
display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap}
.asr .cifra{font-size:2.75rem;font-weight:700;line-height:1}
.mal{color:var(--rojo)}.bien{color:var(--verde)}.regular{color:var(--ambar)}
table{width:100%;border-collapse:collapse;font-size:.875rem}
th{text-align:left;color:var(--suave);font-weight:600;padding:.5rem .75rem;
border-bottom:2px solid var(--borde)}
td{padding:.6rem .75rem;border-bottom:1px solid var(--borde);vertical-align:top}
.barra{height:7px;border-radius:4px;background:var(--borde);overflow:hidden;min-width:90px}
.barra>i{display:block;height:100%}
.hallazgo{background:var(--panel);border:1px solid var(--borde);border-left:4px solid var(--rojo);
border-radius:8px;padding:1rem 1.25rem;margin-bottom:.85rem}
.hallazgo h3{margin:0 0 .35rem;font-size:.95rem;font-family:ui-monospace,monospace}
.etq{display:inline-block;font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;
padding:.15rem .5rem;border-radius:99px;background:var(--borde);color:var(--suave);margin-left:.4rem}
pre{background:var(--fondo);border:1px solid var(--borde);border-radius:6px;padding:.7rem;
overflow-x:auto;font-size:.8rem;margin:.5rem 0 0;white-space:pre-wrap;word-break:break-word}
.campo{color:var(--suave);font-size:.85rem;margin:.2rem 0}
details{margin-top:1rem}summary{cursor:pointer;color:var(--suave);font-size:.875rem}
.ok{background:var(--panel);border:1px solid var(--borde);border-radius:10px;padding:1.5rem;color:var(--suave)}
"""


def _clase(asr: float) -> str:
    return "bien" if asr == 0 else ("regular" if asr < 0.25 else "mal")


def _color(asr: float) -> str:
    return "var(--verde)" if asr == 0 else ("var(--ambar)" if asr < 0.25 else "var(--rojo)")


def _fila_categoria(nombre: str, datos: dict) -> str:
    asr = datos["asr"]
    return (
        f"<tr><td>{html.escape(nombre)}</td>"
        f"<td><b class='{_clase(asr)}'>{asr:.1%}</b></td>"
        f"<td><div class='barra'><i style='width:{asr*100:.0f}%;background:{_color(asr)}'></i></div></td>"
        f"<td>{datos['exitosos']}/{datos['total']}</td></tr>"
    )


def _linea_guardrail(r) -> str:
    """Qué hizo el filtro de entrada con el payload, cuando el objetivo lo registró."""
    g = r.respuesta.crudo.get("guardrail") if isinstance(r.respuesta.crudo, dict) else None
    if g:
        veredicto = "dejó pasar" if g["es_seguro"] else f"BLOQUEÓ · {g['capa']} (motivo: {g['motivo']})"
        return f"<p class=\"campo\"><b>Guardrail:</b> {html.escape(veredicto)} · {g['latencia_ms']:.0f} ms</p>"
    if r.respuesta.bloqueado:
        return f"<p class=\"campo\"><b>Guardrail:</b> BLOQUEÓ · {html.escape(r.respuesta.capa or r.respuesta.motivo)}</p>"
    return ""


def _hallazgo(r) -> str:
    extracto = html.escape(" ".join(r.respuesta.texto.split())[:600]) if r.respuesta.texto else ""
    llm = ""
    if r.veredicto_llm is not None:
        estado = "CEDIÓ" if r.veredicto_llm.exito else ("sin veredicto firme" if r.veredicto_llm.confianza == "baja" else "aguantó")
        llm = f"<p class=\"campo\"><b>LLM solo:</b> {estado} · {html.escape(r.veredicto_llm.detector)} — {html.escape(r.veredicto_llm.evidencia[:200])}</p>"
    if extracto:
        bloque = f"{llm}<p class=\"campo\"><b>Respuesta del agente:</b></p><pre>{extracto}</pre>"
    elif r.respuesta.bloqueado:
        bloque = "<p class=\"campo\"><i>El agente no se ejecutó: el guardrail detuvo el payload en la entrada.</i></p>"
    else:
        bloque = ""
    return f"""<div class="hallazgo">
<h3>{html.escape(r.caso.id)}<span class="etq">{html.escape(r.caso.severidad)}</span>
<span class="etq">{html.escape(r.caso.categoria)}</span>
<span class="etq">{html.escape(r.caso.tecnica)}</span></h3>
<p class="campo"><b>Objetivo del ataque:</b> {html.escape(r.caso.objetivo or '(sin declarar)')}</p>
<p class="campo"><b>Evidencia:</b> {html.escape(r.veredicto.evidencia)}</p>
<p class="campo"><b>Detectado por:</b> {html.escape(r.veredicto.detector)} · confianza {html.escape(r.veredicto.confianza)}</p>
{_linea_guardrail(r)}
<details><summary>Payload enviado</summary><pre>{html.escape(r.caso.payload)}</pre></details>
{bloque}</div>"""


def guardar_html(informe: InformeCorrida, directorio: Path) -> Path:
    directorio.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    ruta = directorio / f"redturing-{informe.objetivo}-{marca}.html"

    asr = informe.asr
    orden = sorted(informe.exitosos, key=lambda x: ORDEN_SEVERIDAD.get(x.caso.severidad, 9))

    if orden:
        hallazgos = "".join(_hallazgo(r) for r in orden)
    else:
        hallazgos = (
            "<div class='ok'>Ningún ataque de esta corpus penetró las defensas. "
            "Eso mide la resistencia frente a estos vectores, no la seguridad del "
            "sistema en general: amplía <code>attacks/</code> y vuelve a correr.</div>"
        )

    filas_cat = "".join(
        _fila_categoria(k, v)
        for k, v in sorted(informe.asr_por("categoria").items(), key=lambda x: -x[1]["asr"])
    )
    filas_todo = "".join(
        f"<tr><td>{html.escape(r.caso.id)}</td><td>{html.escape(r.caso.categoria)}</td>"
        f"<td class='{'mal' if r.veredicto.exito else 'bien'}'>"
        f"{'PENETRÓ' if r.veredicto.exito else 'contenido'}</td>"
        f"<td>{html.escape(r.respuesta.capa or r.veredicto.detector)}</td></tr>"
        for r in informe.resultados
    )

    ruta.write_text(
        f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Red Turing — {html.escape(informe.objetivo)}</title><style>{_ESTILOS}</style></head>
<body><div class="hoja">
<h1>Red Turing</h1>
<p class="meta">Objetivo <b>{html.escape(informe.objetivo)}</b> ({html.escape(informe.tipo_objetivo)})
· {informe.inicio} · {informe.duracion_s:.1f}s
· juez LLM {'activo' if informe.juez_activo else 'inactivo'}</p>

<div class="asr"><span class="cifra {_clase(asr)}">{asr:.1%}</span>
<span>Attack Success Rate<br><span style="color:var(--suave)">
{len(informe.exitosos)} de {len(informe.evaluados)} ataques evaluados penetraron
{f'· {len(informe.errores)} sin medir' if informe.errores else ''}</span></span></div>

<h2>ASR por categoría</h2>
<table><thead><tr><th>Categoría</th><th>ASR</th><th></th><th>Casos</th></tr></thead>
<tbody>{filas_cat}</tbody></table>

<h2>Hallazgos</h2>{hallazgos}

<details><summary>Ver los {informe.total} casos ejecutados</summary>
<table><thead><tr><th>Caso</th><th>Categoría</th><th>Resultado</th><th>Detenido por</th></tr></thead>
<tbody>{filas_todo}</tbody></table></details>
</div></body></html>""",
        encoding="utf-8",
    )
    return ruta
