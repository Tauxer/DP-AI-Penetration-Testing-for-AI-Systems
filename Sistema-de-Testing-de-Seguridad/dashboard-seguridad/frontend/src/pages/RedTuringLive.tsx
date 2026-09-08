import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type EstadoCorrida } from '../api'
import { Fase, Tile, estadoAsr, fecha, pct, seg } from '../components/comunes'

interface Caso { completados: number; total: number; id: string; categoria: string; severidad: string; resultado: 'pen' | 'con' | 'err'; nota: string; evidencia: string; latencia_ms: number; texto: string; bloqueado: boolean; llm: 'cedio' | 'aguanto' | 'revisar' | null; benigno: boolean }
const RES = { pen: <span className="res-pen">▲ Penetró</span>, con: <span className="res-con">● Contenido</span>, err: <span className="res-err">○ Sin medir</span> }
const LLM = { cedio: <span className="res-pen">▲ cedió</span>, aguanto: <span className="res-con">● aguantó</span>, revisar: <span className="res-rev">◌ revisar</span> }

export default function RedTuringLive() {
  const nav = useNavigate()
  const [e, setE] = useState<EstadoCorrida | null>(null)
  const [casos, setCasos] = useState<Caso[]>([])
  const [ahora, setAhora] = useState(Date.now())
  const es = useRef<EventSource | null>(null)
  const log = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let vivo = true
    api.get<EstadoCorrida | null>('/api/redturing/corrida-activa').then(est => {
      if (!vivo || !est) { if (vivo && !est) nav('/redturing/nueva'); return }
      setE(est)
      if (!est.activa) return
      const src = new EventSource(`/api/redturing/eventos?id=${encodeURIComponent(est.id)}&desde=0`)
      es.current = src
      src.addEventListener('inicio', ev => { const d = JSON.parse((ev as MessageEvent).data); setE(x => x && ({ ...x, fase: 'corriendo', total: d.total })) })
      src.addEventListener('caso', ev => { const d = JSON.parse((ev as MessageEvent).data) as Caso & { penetraron: number; contenidos: number; errores: number; asr_parcial: number }; setCasos(c => [...c, d]); setE(x => x && ({ ...x, fase: 'corriendo', completados: d.completados, penetraron: d.penetraron, contenidos: d.contenidos, errores: d.errores, asr_parcial: d.asr_parcial })) })
      src.addEventListener('cancelando', () => setE(x => x && ({ ...x, cancelacion_pedida: true })))
      src.addEventListener('fin', ev => { const d = JSON.parse((ev as MessageEvent).data); src.close(); setE(x => x && ({ ...x, fase: d.cancelada ? 'cancelada' : 'terminada', activa: false, archivo: d.archivo })) })
      src.addEventListener('fallo', ev => { const d = JSON.parse((ev as MessageEvent).data); src.close(); setE(x => x && ({ ...x, fase: 'error', activa: false, mensaje: d.mensaje })) })
    }).catch(() => nav('/redturing/nueva'))
    const t = setInterval(() => setAhora(Date.now()), 1000)
    return () => { vivo = false; es.current?.close(); clearInterval(t) }
  }, [nav])
  useEffect(() => { const c = log.current; if (c && c.scrollHeight - c.scrollTop - c.clientHeight < 120) c.scrollTop = c.scrollHeight }, [casos])

  if (!e) return <div className="nota">Buscando corrida en curso…</div>
  const viva = e.fase === 'preparando' || e.fase === 'corriendo'
  const total = e.total || 0, hechos = e.completados || 0
  const w = (n: number) => (total ? `${(n / total) * 100}%` : '0%')
  const evaluados = hechos - (e.errores || 0)

  return (
    <>
      <header className="cab">
        <h2>{e.objetivo}</h2><span className="etq rt">{e.tipo}</span><Fase fase={e.fase} cancelando={e.cancelacion_pedida} />
        <span className="meta">{fecha(e.inicio)} · {String(e.peticion?.workers ?? '')} workers</span>
        <div className="derecha">
          {viva && <button className="btn" disabled={e.cancelacion_pedida} onClick={() => api.post('/api/redturing/cancelar').catch(() => undefined)}>■ Cancelar</button>}
          {!viva && e.archivo && <Link className="btn btn-neutro" to={`/redturing/corrida/${encodeURIComponent(e.archivo)}`}>Ver informe →</Link>}
          {!viva && <Link className="btn" to="/redturing/nueva">Nueva corrida</Link>}
        </div>
      </header>
      {e.fase === 'error' && <div className="error">La corrida no pudo ejecutarse: {e.mensaje}</div>}
      {e.fase === 'cancelada' && <div className="aviso">Cancelada tras {hechos} casos. {e.archivo ? 'El informe parcial se guardó igual.' : 'No se guardó informe.'}</div>}
      <section className="panel">
        <div className="progreso"><i className="p-pen" style={{ width: w(e.penetraron) }} /><i className="p-con" style={{ width: w(e.contenidos) }} /><i className="p-err" style={{ width: w(e.errores) }} /></div>
        <div className="progreso-pie"><span>{total ? `${hechos} de ${total} casos` : 'cargando casos…'}</span><span>{viva ? seg((ahora - new Date(e.inicio).getTime()) / 1000) : ''}</span></div>
      </section>
      <section className="tiles">
        <Tile rot="ASR parcial" val={evaluados ? pct(e.asr_parcial) : '—'} sub="sobre los casos ya evaluados" estado={evaluados ? estadoAsr(e.asr_parcial) : { c: 'neutro', t: 'sin casos evaluados aún' }} />
        <Tile rot="Penetraron" val={<span className="res-pen">{e.penetraron}</span>} sub="la defensa falló" />
        <Tile rot="Contenidos" val={<span className="res-con">{e.contenidos}</span>} sub="el ataque no prosperó" />
        <Tile rot="Sin medir" val={e.errores} sub="error del objetivo o fail-close" />
      </section>
      <section className="panel">
        <h3>Casos conforme terminan</h3><p className="desc">Con varios workers el orden de llegada no es el de la corpus.</p>
        <div className="log" ref={log}><table>
          <thead><tr><th>#</th><th>Resultado</th><th>Caso</th><th>Categoría</th><th>Sev.</th><th>Guardrail / detector</th><th>LLM solo</th><th>Respuesta del agente</th><th style={{ textAlign: 'right' }}>ms</th></tr></thead>
          <tbody>{casos.map(c => (
            <tr key={c.id}><td className="mono">{c.completados}/{c.total}</td><td>{RES[c.resultado]}{c.benigno && <> <span className="etq">control</span></>}</td><td className="mono">{c.id}</td><td>{c.categoria}</td><td><span className={`sev sev-${c.severidad}`}>{c.severidad}</span></td><td title={c.evidencia}>{c.nota}</td>
              <td>{c.llm ? <>{LLM[c.llm]}{c.llm === 'cedio' && c.bloqueado && <> <span className="etq">tapado</span></>}</> : <span className="res-err">—</span>}</td>
              <td className="resp">{c.texto ? <div className="txt" title={c.texto}>{c.texto}</div> : <span className="mudo">{c.bloqueado ? 'no se ejecutó: detenido en la entrada' : c.resultado === 'err' ? 'sin medir' : '—'}</span>}</td><td className="mono" style={{ textAlign: 'right' }}>{c.latencia_ms}</td></tr>
          ))}</tbody>
        </table></div>
      </section>
    </>
  )
}
