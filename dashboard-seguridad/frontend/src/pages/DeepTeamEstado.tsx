import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type EstadoDT } from '../api'
import { Fase, fecha, seg } from '../components/comunes'
import ResumenErrores from '../components/ResumenErrores'

export default function DeepTeamEstado() {
  const nav = useNavigate()
  const [e, setE] = useState<EstadoDT | null | undefined>(undefined)
  const [ahora, setAhora] = useState(Date.now())
  useEffect(() => {
    let vivo = true
    const tick = () => api.get<EstadoDT | null>('/api/deepteam/estado').then(x => { if (vivo) setE(x) }).catch(() => undefined)
    tick()
    const t = setInterval(() => { tick(); setAhora(Date.now()) }, 2000)
    return () => { vivo = false; clearInterval(t) }
  }, [])
  useEffect(() => { if (e === null) nav('/deepteam/nueva') }, [e, nav])
  if (!e) return <div className="nota">Buscando evaluación…</div>
  const viva = e.activa
  const p = e.peticion as { modelo_adversario?: string; modelo_juez?: string; con_guardrail?: boolean; ataques?: string[]; vulnerabilidades?: { nombre: string }[] }
  const pctAvance = e.total_estimado ? Math.min(100, (e.llamadas_al_agente / e.total_estimado) * 100) : 0
  return (
    <>
      <header className="cab">
        <h2>Evaluación DeepTeam</h2><Fase fase={e.fase} />
        <span className="meta">{fecha(e.inicio)} · adversario <code>{p.modelo_adversario}</code> · juez <code>{p.modelo_juez}</code> · {p.con_guardrail ? 'sistema completo' : 'solo LLM'}</span>
        <div className="derecha">
          {!viva && e.archivo && <Link className="btn btn-neutro" to={`/deepteam/evaluacion/${encodeURIComponent(e.archivo)}`}>Ver evaluación →</Link>}
          {!viva && <Link className="btn" to="/deepteam/nueva">Nueva evaluación</Link>}
        </div>
      </header>
      {e.fase === 'error' && <div className="error">La evaluación falló antes de empezar: {e.mensaje}</div>}
      {!viva && e.resultado && <ResumenErrores r={e.resultado} />}
      <section className="panel">
        <div className="progreso"><i className="p-dt" style={{ width: `${pctAvance}%` }} /></div>
        <div className="progreso-pie"><span>{e.llamadas_al_agente} llamadas a TramiBot de ≈ {e.total_estimado} previstas</span><span>{viva ? seg((ahora - new Date(e.inicio).getTime()) / 1000) : seg(e.duracion_s)}</span></div>
      </section>
      <section className="panel">
        <h3>Qué está pasando</h3>
        <p className="desc">DeepTeam no emite eventos por caso: primero el adversario genera todos los payloads, luego los envía a TramiBot y al final el juez los evalúa. La barra avanza con las llamadas al agente.</p>
        <dl className="kv">
          <dt>Vulnerabilidades</dt><dd>{(p.vulnerabilidades ?? []).map(v => v.nombre).join(', ')}</dd>
          <dt>Métodos</dt><dd>{(p.ataques ?? []).join(', ')}</dd>
        </dl>
        {viva && <div className="aviso">No cierres el backend mientras corre. DeepTeam no admite cancelación limpia; si hace falta, detén el servidor.</div>}
      </section>
    </>
  )
}
