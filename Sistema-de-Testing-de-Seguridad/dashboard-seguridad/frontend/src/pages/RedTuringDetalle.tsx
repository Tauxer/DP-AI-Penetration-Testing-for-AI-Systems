import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type CorridaResumen, type Informe, type Resultado } from '../api'
import { Barra, Tile, estadoAsr, fecha, pct, useCarga } from '../components/comunes'

type Res = 'todos' | 'pen' | 'con' | 'err' | 'llm'
const tipoRes = (r: Resultado) => (r.respuesta.error ? 'err' : r.veredicto.exito ? 'pen' : 'con')
const ORDEN_SEV: Record<string, number> = { critica: 0, alta: 1, media: 2, baja: 3 }

function veredictoGuardrail(r: Resultado, tipoObjetivo: string) {
  const x = r.respuesta, g = x.crudo?.guardrail
  if (g) return g.es_seguro ? { paso: true, texto: 'dejó pasar', detalle: `es_seguro = true · ${Math.round(g.latencia_ms)} ms` } : { paso: false, texto: `bloqueó · ${g.capa}`, detalle: `motivo: ${g.motivo}` }
  if (x.bloqueado) return { paso: false, texto: `bloqueó · ${x.capa || x.motivo}`, detalle: x.capa?.includes('inferido') ? 'inferido de la respuesta' : `motivo: ${x.motivo}` }
  if (tipoObjetivo === 'guardrail') return { paso: true, texto: 'dejó pasar', detalle: 'es_seguro = true' }
  if (x.error) return null
  return { paso: true, texto: 'dejó pasar', detalle: 'el agente respondió sin señal de bloqueo' }
}
const estadoLlm = (r: Resultado) => (!r.veredicto_llm ? null : r.veredicto_llm.exito ? 'cedio' : r.veredicto_llm.confianza === 'baja' ? 'revisar' : 'aguanto')
const LLM = { cedio: <span className="res-pen">▲ cedió</span>, aguanto: <span className="res-con">● aguantó</span>, revisar: <span className="res-rev">◌ revisar</span> }

export default function RedTuringDetalle() {
  const { archivo = '' } = useParams()
  const nav = useNavigate()
  const { datos: d, error } = useCarga(() => api.get<Informe>(`/api/redturing/corrida?archivo=${encodeURIComponent(archivo)}`), [archivo])
  const { datos: corridas } = useCarga(() => api.get<CorridaResumen[]>('/api/redturing/corridas'), [])
  const [f, setF] = useState<{ texto: string; res: Res; cat: string; sev: string }>({ texto: '', res: 'todos', cat: '', sev: '' })
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set())
  const [base, setBase] = useState('')
  const { datos: cmp } = useCarga(() => (base ? api.get<Record<string, never>>(`/api/redturing/comparar?antes=${encodeURIComponent(base)}&despues=${encodeURIComponent(archivo)}`) : Promise.resolve(null)), [base, archivo])

  const filas = useMemo(() => {
    if (!d) return []
    const q = f.texto.toLowerCase()
    return d.resultados
      .filter(r => (f.res === 'todos' || (f.res === 'llm' ? !!r.veredicto_llm?.exito : tipoRes(r) === f.res)) && (!f.cat || r.caso.categoria === f.cat) && (!f.sev || r.caso.severidad === f.sev)
        && (!q || [r.caso.id, r.caso.tecnica, r.caso.objetivo, r.veredicto.evidencia, r.respuesta.capa, r.respuesta.texto].join(' ').toLowerCase().includes(q)))
      .sort((a, b) => { const ta = tipoRes(a), tb = tipoRes(b); const o = (t: string) => (t === 'pen' ? 0 : t === 'con' ? 1 : 2); return o(ta) - o(tb) || (ORDEN_SEV[a.caso.severidad] ?? 9) - (ORDEN_SEV[b.caso.severidad] ?? 9) || a.caso.id.localeCompare(b.caso.id) })
  }, [d, f])

  if (error) return <div className="error">No se pudo cargar el informe: {error}</div>
  if (!d) return <div className="nota">Cargando…</div>
  const r = d.resumen, e = estadoAsr(r.asr)
  const fp = d.asr_por_categoria?.control_falsos_positivos
  const hayLlm = r.asr_llm !== null && r.asr_llm !== undefined && (r.evaluados_llm ?? 0) > 0
  const tapados = d.resultados.filter(x => x.veredicto_llm?.exito && x.respuesta.bloqueado).length
  const cats = Object.entries(d.asr_por_categoria).sort((a, b) => b[1].asr - a[1].asr)
  const capas = Object.entries(d.asr_por_capa_que_bloqueo).filter(([k]) => k !== '(sin bloqueo)').sort((a, b) => b[1].total - a[1].total)
  const otras = (corridas ?? []).filter(c => c.objetivo === d.objetivo && c.archivo !== archivo)
  const toggle = (id: string) => setAbiertos(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  return (
    <>
      <header className="cab">
        <h2>{d.objetivo}</h2><span className="etq rt">{d.tipo_objetivo}</span>
        <span className="meta">{fecha(d.inicio)} · {d.duracion_s}s · juez LLM {d.juez_activo ? 'activo' : 'inactivo'} · mediana {Math.round(r.latencia_mediana_ms)} ms/caso</span>
        <div className="derecha">
          <Link className="btn" to="/redturing">← Corridas</Link>
          <button className="btn" onClick={() => nav('/redturing/nueva', { state: { objetivo: d.objetivo, suites: [...new Set(d.resultados.map(x => x.caso.archivo_origen.replace(/\.yaml$/, '')))], juez: d.juez_activo } })}>↻ Repetir corrida</button>
        </div>
      </header>

      <section className="tiles">
        {hayLlm && <Tile destacada rot="ASR solo LLM" val={pct(r.asr_llm)} sub={`${r.cedidos_llm} de ${r.evaluados_llm} veces cedió el modelo${tapados ? ` · ${tapados} tapadas por el guardrail` : ''}`} estado={r.asr_llm === 0 ? { c: 'ok', t: 'el prompt aguantó todo' } : estadoAsr(r.asr_llm!)} />}
        <Tile rot="Attack Success Rate" val={pct(r.asr)} sub={`${r.exitosos} de ${r.evaluados} ataques evaluados penetraron`} estado={e} />
        <Tile rot="Falsos positivos" val={fp ? pct(fp.asr) : '—'} sub="mensajes legítimos bloqueados" estado={fp ? (fp.asr === 0 ? { c: 'ok', t: 'ningún usuario legítimo bloqueado' } : { c: 'serio', t: `${fp.exitosos} de ${fp.total} controles bloqueados` }) : { c: 'neutro', t: 'la suite controles no corrió' }} />
        <Tile rot="Casos evaluados" val={r.evaluados} sub={`de ${r.total} lanzados`} />
        <Tile rot="Sin medir" val={r.errores} sub="fuera del ASR: el objetivo o una capa no respondió" />
      </section>

      <section className="fila">
        <div className="panel">
          <h3>ASR por categoría</h3><p className="desc">Clic para filtrar los hallazgos.</p>
          <div className="barras">{cats.map(([k, v]) => <Barra key={k} nombre={k} valor={v.asr} max={1} clase={`f-${estadoAsr(v.asr).c}`} num={<b>{pct(v.asr)}</b>} sel={f.cat === k} onClick={() => setF({ ...f, cat: f.cat === k ? '' : k })} />)}</div>
        </div>
        <div className="panel">
          <h3>Qué capa detuvo cada ataque</h3><p className="desc">Un fail-close no cuenta como defensa.</p>
          <div className="barras">{capas.length ? capas.map(([k, v]) => <Barra key={k} nombre={k} valor={v.total} max={Math.max(1, ...capas.map(([, x]) => x.total))} clase="f-serie" num={<b>{v.total}</b>} />) : <div className="nota">Ningún bloqueo en esta corrida.</div>}</div>
        </div>
      </section>

      <section className="panel">
        <h3>Comparar con otra corrida</h3><p className="desc">Regresiones: ataques que antes se paraban y ahora entran.</p>
        <select value={base} onChange={ev => setBase(ev.target.value)}>
          <option value="">— elegir corrida —</option>
          {otras.map(c => <option key={c.archivo} value={c.archivo}>{fecha(c.inicio)}{c.es_baseline ? ' (baseline)' : ''} · {pct(c.asr)}</option>)}
        </select>
        {cmp && (
          <div className="kv" style={{ marginTop: 12 }}>
            {(['regresiones', 'corregidos', 'primera_medicion', 'casos_nuevos', 'casos_retirados', 'sin_medir_ahora'] as const).map(k => {
              const items = (cmp as unknown as Record<string, { id: string }[]>)[k] ?? []
              return <><dt key={k + 'k'}>{k.replace('_', ' ')}</dt><dd key={k + 'v'} className={k === 'regresiones' && items.length ? 'res-pen' : ''}>{items.length ? items.map(i => i.id).join(', ') : 'ninguno'}</dd></>
            })}
          </div>
        )}
      </section>

      <section className="panel">
        <h3>Hallazgos</h3><p className="desc">Clic en una fila para ver el payload, el veredicto del guardrail, el del LLM y la respuesta completa.</p>
        <div className="filtros">
          <input type="search" placeholder="Buscar en id, técnica, evidencia, respuesta…" value={f.texto} onChange={ev => setF({ ...f, texto: ev.target.value })} />
          <div className="seg">{(['todos', 'pen', 'con', 'err', 'llm'] as Res[]).map(v => <button key={v} className={f.res === v ? 'on' : ''} onClick={() => setF({ ...f, res: v })}>{{ todos: 'Todos', pen: 'Penetró', con: 'Contenido', err: 'Sin medir', llm: 'LLM cedió' }[v]}</button>)}</div>
          <select value={f.cat} onChange={ev => setF({ ...f, cat: ev.target.value })}><option value="">Todas las categorías</option>{cats.map(([k]) => <option key={k}>{k}</option>)}</select>
          <select value={f.sev} onChange={ev => setF({ ...f, sev: ev.target.value })}><option value="">Toda severidad</option>{['critica', 'alta', 'media', 'baja'].map(s => <option key={s}>{s}</option>)}</select>
        </div>
        <div className="scroll">
          <table>
            <thead><tr><th>Caso</th><th>Categoría</th><th>Técnica</th><th>Sev.</th><th>Resultado</th><th>Guardrail</th><th>LLM solo</th><th>Respuesta del agente</th></tr></thead>
            <tbody>
              {filas.map(x => {
                const t = tipoRes(x), g = veredictoGuardrail(x, d.tipo_objetivo), l = estadoLlm(x)
                const malo = x.caso.benigno ? !g?.paso : g?.paso
                const abierto = abiertos.has(x.caso.id)
                return (
                  <>
                    <tr key={x.caso.id} className="clic" onClick={() => toggle(x.caso.id)}>
                      <td className="mono">{x.caso.id}</td><td>{x.caso.categoria}</td><td>{x.caso.tecnica}</td>
                      <td><span className={`sev sev-${x.caso.severidad}`}>{x.caso.severidad}</span></td>
                      <td>{t === 'pen' ? <span className="res-pen">▲ Penetró</span> : t === 'err' ? <span className="res-err">○ Sin medir</span> : x.veredicto.confianza === 'baja' ? <span className="res-rev" title="Ningún detector cerró el caso y el juez no actuó">◌ Contenido · revisar</span> : <span className="res-con">● Contenido</span>}</td>
                      <td>{g ? <span className={malo ? 'res-pen' : 'res-con'} title={g.detalle}>{g.paso ? '→ ' : '■ '}{g.texto}</span> : <span className="res-err">—</span>}</td>
                      <td>{l ? <>{LLM[l]}{l === 'cedio' && x.respuesta.bloqueado && <> <span className="etq" title="El guardrail lo paró, pero el modelo habría cedido">tapado</span></>}</> : <span className="res-err">—</span>}</td>
                      <td className="resp">{x.respuesta.texto ? <div className="txt" title={x.respuesta.texto.slice(0, 600)}>{x.respuesta.texto}</div> : x.respuesta.error ? <span className="mudo">sin medir: {x.respuesta.error.slice(0, 80)}</span> : x.respuesta.bloqueado ? <span className="mudo">no se ejecutó: detenido en la entrada</span> : d.tipo_objetivo === 'guardrail' ? <span className="mudo">no aplica: corrida solo de guardrail</span> : <span className="mudo">respuesta vacía</span>}</td>
                    </tr>
                    {abierto && (
                      <tr key={x.caso.id + '-det'} className="det"><td colSpan={8}><div className="det-grid">
                        <div>
                          <h5>Objetivo del ataque</h5><p>{x.caso.objetivo || '(sin declarar)'}</p>
                          <h5>Evidencia · {x.veredicto.detector} (confianza {x.veredicto.confianza})</h5><p>{x.veredicto.evidencia}</p>
                          {x.respuesta.error && <><h5>Error</h5><p>{x.respuesta.error}</p></>}
                          {x.caso.notas && <><h5>Notas</h5><p>{x.caso.notas}</p></>}
                          <h5>Payload enviado</h5><pre>{x.caso.payload}</pre>
                        </div>
                        <div>
                          <h5>Guardrail de entrada</h5>
                          {g ? <div className={`veredicto ${malo ? 'paso' : 'paro'}`}><b>{g.paso ? '→ Dejó pasar' : '■ Bloqueó'}</b><span>{g.texto.replace(/^(dejó pasar|bloqueó · )/, '')}</span><span className="m">{g.detalle}</span></div> : <div className="veredicto"><span className="mudo">sin veredicto: el objetivo no respondió</span></div>}
                          <h5>Respuesta del agente{x.respuesta.crudo?.llm_pese_al_bloqueo && <> · <span className="etq">recibió el payload pese al bloqueo</span></>}</h5>
                          {x.veredicto_llm && <div className={`veredicto ${x.veredicto_llm.exito ? 'paso' : 'paro'}`}><b>LLM solo: {l === 'cedio' ? '▲ cedió' : l === 'aguanto' ? '● aguantó' : '◌ revisar'}</b><span>{x.veredicto_llm.evidencia}</span><span className="m">{x.veredicto_llm.detector} · conf. {x.veredicto_llm.confianza}</span></div>}
                          <pre>{x.respuesta.texto || (x.respuesta.bloqueado ? 'El agente no se ejecutó: el guardrail detuvo el payload en la entrada.' : d.tipo_objetivo === 'guardrail' ? 'Corrida solo de guardrail: el agente nunca se ejecuta.' : '(respuesta vacía)')}</pre>
                        </div>
                      </div></td></tr>
                    )}
                  </>
                )
              })}
              {!filas.length && <tr><td colSpan={8} className="nota">Ningún caso coincide con los filtros.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="pie">{filas.length} de {d.resultados.length} casos</div>
      </section>
    </>
  )
}
