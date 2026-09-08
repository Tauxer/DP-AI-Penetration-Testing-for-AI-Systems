import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type CasoDT, type Evaluacion } from '../api'
import { Barra, Tile, estadoAsr, fecha, pct, useCarga } from '../components/comunes'
import ResumenErrores from '../components/ResumenErrores'

type Res = 'todos' | 'fallo' | 'ok' | 'err'
const tipo = (c: CasoDT) => (c.error ? 'err' : c.score === 0 ? 'fallo' : c.score === null ? 'err' : 'ok')

export default function DeepTeamDetalle() {
  const { archivo = '' } = useParams()
  const { datos: d, error } = useCarga(() => api.get<Evaluacion>(`/api/deepteam/evaluacion?archivo=${encodeURIComponent(archivo)}`), [archivo])
  const [f, setF] = useState<{ texto: string; res: Res; vuln: string }>({ texto: '', res: 'todos', vuln: '' })
  const [abiertos, setAbiertos] = useState<Set<number>>(new Set())

  const filas = useMemo(() => {
    if (!d) return []
    const q = f.texto.toLowerCase()
    return d.casos.map((c, i) => ({ c, i })).filter(({ c }) => (f.res === 'todos' || tipo(c) === f.res) && (!f.vuln || c.vulnerabilidad === f.vuln)
      && (!q || [c.vulnerabilidad, c.tipo, c.ataque, c.payload, c.respuesta_tramibot, c.razon_juez].join(' ').toLowerCase().includes(q)))
      .sort((a, b) => { const o = (t: string) => (t === 'fallo' ? 0 : t === 'ok' ? 1 : 2); return o(tipo(a.c)) - o(tipo(b.c)) })
  }, [d, f])

  if (error) return <div className="error">No se pudo cargar la evaluación: {error}</div>
  if (!d) return <div className="nota">Cargando…</div>
  const evaluados = d.casos.filter(c => tipo(c) !== 'err'), fallidos = d.casos.filter(c => tipo(c) === 'fallo'), errores = d.casos.length - evaluados.length
  const tasa = evaluados.length ? fallidos.length / evaluados.length : 0
  const porVuln = d.por_vulnerabilidad ?? []
  const porAtaque = d.por_ataque ?? []
  const vulns = [...new Set(d.casos.map(c => c.vulnerabilidad))]
  const costeTotal = d.casos.reduce((s, c) => s + (c.coste_simulacion ?? 0) + (c.coste_evaluacion ?? 0), 0)
  const toggle = (i: number) => setAbiertos(s => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n })

  return (
    <>
      <header className="cab">
        <h2>{d.etiqueta || 'Evaluación DeepTeam'}</h2>{d.objetivo && <span className="etq">{d.objetivo}</span>}<span className="etq dt">{d.modo}</span>
        <span className="meta">{fecha(d.inicio)} · {d.duracion_s}s{d.llamadas_al_agente ? ` · ${d.llamadas_al_agente} llamadas a TramiBot` : ''}</span>
        <div className="derecha"><Link className="btn" to="/deepteam">← Evaluaciones</Link><Link className="btn btn-dt" to="/deepteam/nueva">＋ Nueva evaluación</Link></div>
      </header>

      <section className="tiles">
        <Tile destacada rot="Tasa de fallo" val={pct(tasa)} sub={`${fallidos.length} de ${evaluados.length} casos: el juez vio ceder al agente`} estado={tasa === 0 ? { c: 'ok', t: 'ningún fallo según el juez' } : estadoAsr(tasa)} />
        <Tile rot="Modelo adversario" val={<span style={{ fontSize: 18 }}>{d.modelo_adversario ?? '—'}</span>} sub="inventa y mejora los ataques" />
        <Tile rot="Modelo juez" val={<span style={{ fontSize: 18 }}>{d.modelo_juez ?? '—'}</span>} sub="decide 0 / 1 con una razón" />
        <Tile rot="CVSS" val={d.cvss === null || d.cvss === undefined ? '—' : d.cvss.toFixed(1)} sub="puntuación de riesgo de DeepTeam (0-10)" />
        <Tile rot="Con error" val={errores} sub="el objetivo o el adversario no respondieron" />
      </section>

      {d.resultado && d.resultado.errores > 0 && <ResumenErrores r={d.resultado} compacto />}

      <section className="fila">
        <div className="panel">
          <h3>Fallos por vulnerabilidad</h3><p className="desc">DeepTeam reporta tasa de mitigación; aquí se muestra su inverso, la tasa de fallo, para leerla igual que el ASR.</p>
          <div className="barras">{porVuln.length ? porVuln.map(v => <Barra key={v.vulnerabilidad + v.tipo} nombre={`${v.vulnerabilidad} · ${v.tipo}`} valor={1 - v.tasa_mitigacion} max={1} clase={`f-${estadoAsr(1 - v.tasa_mitigacion).c}`} num={<b>{v.fallidos}/{v.fallidos + v.aprobados}</b>} onClick={() => setF({ ...f, vuln: f.vuln === v.vulnerabilidad ? '' : v.vulnerabilidad })} sel={f.vuln === v.vulnerabilidad} />) : <div className="nota">Esta evaluación no guardó el desglose.</div>}</div>
        </div>
        <div className="panel">
          <h3>Fallos por método de ataque</h3><p className="desc">Qué técnica del adversario funcionó mejor contra TramiBot.</p>
          <div className="barras">{porAtaque.length ? porAtaque.map(a => <Barra key={a.ataque} nombre={a.ataque} valor={1 - a.tasa_mitigacion} max={1} clase="f-dt" num={<b>{a.fallidos}/{a.fallidos + a.aprobados}</b>} />) : <div className="nota">Sin desglose.</div>}</div>
          {costeTotal > 0 && <div className="pie">Coste DeepTeam (adversario + juez): ${costeTotal.toFixed(4)}. TramiBot aparte.</div>}
        </div>
      </section>

      <section className="panel">
        <h3>Casos</h3><p className="desc">Clic en una fila para ver el payload completo, la respuesta de TramiBot y la razón del juez.</p>
        <div className="filtros">
          <input type="search" placeholder="Buscar en payload, respuesta, razón…" value={f.texto} onChange={e => setF({ ...f, texto: e.target.value })} />
          <div className="seg">{(['todos', 'fallo', 'ok', 'err'] as Res[]).map(v => <button key={v} className={f.res === v ? 'on' : ''} onClick={() => setF({ ...f, res: v })}>{{ todos: 'Todos', fallo: 'Cedió', ok: 'Aguantó', err: 'Error' }[v]}</button>)}</div>
          <select value={f.vuln} onChange={e => setF({ ...f, vuln: e.target.value })}><option value="">Todas las vulnerabilidades</option>{vulns.map(v => <option key={v}>{v}</option>)}</select>
        </div>
        <div className="scroll"><table>
          <thead><tr><th>Vulnerabilidad</th><th>Tipo</th><th>Ataque</th><th>Veredicto</th><th>Payload</th><th>Respuesta del agente</th></tr></thead>
          <tbody>{filas.map(({ c, i }) => {
            const t = tipo(c)
            return (
              <>
                <tr key={i} className="clic" onClick={() => toggle(i)}>
                  <td>{c.vulnerabilidad}</td><td className="mono">{c.tipo}</td><td>{c.ataque}</td>
                  <td>{t === 'fallo' ? <span className="res-pen">▲ Cedió</span> : t === 'ok' ? <span className="res-con">● Aguantó</span> : <span className="res-err">○ Error</span>}</td>
                  <td className="resp"><div className="txt">{c.payload}</div></td>
                  <td className="resp">{c.respuesta_tramibot ? <div className="txt">{c.respuesta_tramibot}</div> : <span className="mudo">{c.error || 'sin respuesta'}</span>}</td>
                </tr>
                {abiertos.has(i) && (
                  <tr key={i + 'd'} className="det"><td colSpan={6}><div className="det-grid">
                    <div>
                      <h5>Payload del adversario ({c.ataque})</h5><pre>{c.payload}</pre>
                      {c.turnos.length > 0 && <><h5>Conversación multi-turno</h5><pre>{c.turnos.map(t => `[${t.rol}] ${t.contenido}`).join('\n\n')}</pre></>}
                    </div>
                    <div>
                      <h5>Respuesta del agente</h5><pre>{c.respuesta_tramibot || c.error || '(sin respuesta)'}</pre>
                      <h5>Razón del juez · score {c.score ?? '—'}</h5><p>{c.razon_juez || '(sin razón)'}</p>
                      {(c.coste_simulacion || c.coste_evaluacion) && <div className="pie">coste adversario ${(c.coste_simulacion ?? 0).toFixed(5)} · juez ${(c.coste_evaluacion ?? 0).toFixed(5)}</div>}
                    </div>
                  </div></td></tr>
                )}
              </>
            )
          })}
          {!filas.length && <tr><td colSpan={6} className="nota">Ningún caso coincide.</td></tr>}</tbody>
        </table></div>
        <div className="pie">{filas.length} de {d.casos.length} casos</div>
      </section>
    </>
  )
}
