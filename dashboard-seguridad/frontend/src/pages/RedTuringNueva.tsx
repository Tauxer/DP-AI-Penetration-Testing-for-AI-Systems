import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ApiError, api, type EstadoCorrida, type Objetivo, type Plan } from '../api'
import { Barra, useCarga } from '../components/comunes'

export default function RedTuringNueva() {
  const nav = useNavigate()
  const prefijado = (useLocation().state ?? {}) as { objetivo?: string; suites?: string[]; juez?: boolean }
  const { datos: objetivos } = useCarga(() => api.get<Objetivo[]>('/api/redturing/objetivos'), [])
  const { datos: suites } = useCarga(() => api.get<Record<string, number>>('/api/redturing/suites'), [])
  const { datos: juez } = useCarga(() => api.get<{ disponible: boolean; motivo: string; modelo: string }>('/api/redturing/juez'), [])

  const [f, setF] = useState({ objetivo: prefijado.objetivo ?? '', suites: new Set<string>(prefijado.suites ?? []), sev: '', limite: '', workers: 4, juez: prefijado.juez ?? true, html: true })
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmar, setConfirmar] = useState<{ tipo: string; casos: number } | null>(null)
  const [confirmo, setConfirmo] = useState(false)

  useEffect(() => {
    if (objetivos && !f.objetivo) setF(x => ({ ...x, objetivo: (objetivos.find(o => !o.con_coste) ?? objetivos[0])?.nombre ?? '' }))
  }, [objetivos]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (suites && !f.suites.size && !prefijado.suites) setF(x => ({ ...x, suites: new Set(Object.keys(suites)) }))
  }, [suites]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (juez && !juez.disponible) setF(x => ({ ...x, juez: false })) }, [juez])

  const params = useMemo(() => {
    const todas = Object.keys(suites ?? {})
    const sel = [...f.suites].filter(s => todas.includes(s))
    return { objetivo: f.objetivo, suites: sel.length === todas.length ? null : sel, severidad: f.sev || null, limite: f.limite ? +f.limite : null, workers: f.workers, usar_juez: f.juez, generar_html: f.html }
  }, [f, suites])

  useEffect(() => {
    if (!f.objetivo || !f.suites.size) { setPlan(null); return }
    const q = new URLSearchParams({ objetivo: f.objetivo, workers: String(f.workers), usar_juez: f.juez ? '1' : '0' })
    if (params.suites) q.set('suites', params.suites.join(','))
    if (f.sev) q.set('severidad', f.sev)
    if (f.limite) q.set('limite', f.limite)
    const t = setTimeout(() => api.get<Plan>('/api/redturing/plan?' + q).then(p => { setPlan(p); setError(null) }).catch(e => { setPlan(null); setError(e.message) }), 150)
    return () => clearTimeout(t)
  }, [params, f]) // eslint-disable-line react-hooks/exhaustive-deps

  const obj = objetivos?.find(o => o.nombre === f.objetivo)

  async function lanzar(conf: boolean) {
    setError(null)
    try {
      await api.post<EstadoCorrida>('/api/redturing/correr', { ...params, confirmar: conf })
      nav('/redturing/live')
    } catch (e) {
      const err = e as ApiError
      if (err.cuerpo?.requiere_confirmacion) { setConfirmar({ tipo: String(err.cuerpo.tipo), casos: Number(err.cuerpo.casos) }); return }
      if (err.estado === 409) { nav('/redturing/live'); return }
      setError(err.message)
    }
  }

  const explica: Record<string, string> = { guardrail: 'Solo el filtro de entrada. Milisegundos por caso, coste cero.', agente: 'Guardrail + LLM. Una llamada real al modelo por caso.', http: 'Servicio remoto por HTTP. Una petición real por caso.', simulado: 'Objetivo de mentira para verificar el arnés. Sin coste.' }

  return (
    <>
      <header className="cab"><h2>Nueva corrida</h2><span className="etq rt">Red Turing</span><span className="meta">Los mismos parámetros que <code>python -m redturing correr</code>. Nada se envía hasta que pulses lanzar.</span></header>
      <div className="form-grid">
        <section className="panel">
          <div className="campo">
            <label>Objetivo</label>
            <select value={f.objetivo} onChange={e => setF({ ...f, objetivo: e.target.value })}>{(objetivos ?? []).map(o => <option key={o.nombre} value={o.nombre}>{o.nombre} · {o.tipo}</option>)}</select>
            {obj && <div className="ayuda">{obj.con_coste ? <span className="etq rojo">CUESTA</span> : <span className="etq">GRATIS</span>} {explica[obj.tipo]} <code>{obj.destino}</code></div>}
          </div>
          <div className="campo">
            <span className="rot">Suites de ataque</span>
            <div className="chips">{Object.entries(suites ?? {}).map(([s, n]) => <button key={s} type="button" className={`chip ${f.suites.has(s) ? 'on' : ''}`} onClick={() => { const c = new Set(f.suites); c.has(s) ? c.delete(s) : c.add(s); setF({ ...f, suites: c }) }}>{s} <span className="n">{n}</span></button>)}</div>
            <div className="ayuda">Clic para activar o desactivar. <button className="btn chico" onClick={() => setF({ ...f, suites: new Set(Object.keys(suites ?? {})) })}>Todas</button> <button className="btn chico" onClick={() => setF({ ...f, suites: new Set() })}>Ninguna</button></div>
          </div>
          <div className="campo doble">
            <div><label>Severidad mínima</label><select value={f.sev} onChange={e => setF({ ...f, sev: e.target.value })}><option value="">Todas</option><option value="media">Media o superior</option><option value="alta">Alta o superior</option><option value="critica">Solo crítica</option></select></div>
            <div><label>Límite de casos</label><input type="number" min={1} placeholder="sin límite" value={f.limite} onChange={e => setF({ ...f, limite: e.target.value })} /></div>
          </div>
          <div className="campo doble">
            <div><label>Ataques en paralelo</label><input type="number" min={1} max={16} value={f.workers} onChange={e => setF({ ...f, workers: Math.min(16, Math.max(1, +e.target.value || 1)) })} /><div className="ayuda">1 para depurar. Contra el agente, 2 evita saturar el LLM.</div></div>
            <div>
              <span className="rot">Opciones</span>
              <label className="check" style={{ opacity: juez?.disponible ? 1 : .6 }}><input type="checkbox" checked={f.juez && !!juez?.disponible} disabled={!juez?.disponible} onChange={e => setF({ ...f, juez: e.target.checked })} /><span>Juez LLM<span className="ayuda">{juez?.disponible ? `${juez.modelo} decide los casos que las reglas no cierran.` : `No disponible: ${juez?.motivo ?? '…'}. Solo detectores determinísticos.`}</span></span></label>
              <label className="check"><input type="checkbox" checked={f.html} onChange={e => setF({ ...f, html: e.target.checked })} /><span>Generar informe HTML<span className="ayuda">Además del JSON, un HTML autocontenido.</span></span></label>
            </div>
          </div>
        </section>

        <aside className="panel plan">
          <h3>Qué se va a lanzar</h3><p className="desc">Se recalcula con cada cambio. No envía nada.</p>
          {!f.suites.size && <div className="nota">Elige al menos una suite.</div>}
          {plan && (
            <>
              <div className="grande">{plan.total}<small>casos</small></div>
              <div className="sub">{plan.total - plan.benignos} ataques · {plan.benignos} controles legítimos</div>
              <h4>Por categoría</h4>
              <div className="barras">{Object.entries(plan.por_categoria).sort((a, b) => b[1] - a[1]).map(([k, n]) => <Barra key={k} nombre={k} valor={n} max={Math.max(1, ...Object.values(plan.por_categoria))} clase="f-serie" num={<b>{n}</b>} />)}</div>
              {plan.con_coste ? <div className="coste"><b>{plan.total} llamadas reales</b> a <code>{plan.objetivo}</code> (tipo {plan.tipo}). Cada una consume tokens y deja traza.</div> : <div className="gratis">Objetivo de tipo <b>{plan.tipo}</b>: sin coste por caso.</div>}
            </>
          )}
          {error && <div className="error">{error}</div>}
          {!confirmar ? (
            <div className="acciones"><button className="btn btn-rt" disabled={!plan || plan.total === 0} onClick={() => lanzar(false)}>Lanzar corrida</button></div>
          ) : (
            <div className="confirmar">
              <h4>Esta corrida cuesta dinero</h4>
              <p>Vas a enviar <b>{confirmar.casos} payloads</b> a <code>{f.objetivo}</code> (tipo <b>{confirmar.tipo}</b>). Cada caso es una llamada al LLM y dejará traza en Langfuse.</p>
              <label className="check"><input type="checkbox" checked={confirmo} onChange={e => setConfirmo(e.target.checked)} /><span>Entiendo el coste.</span></label>
              <div className="acciones"><button className="btn btn-rt" disabled={!confirmo} onClick={() => lanzar(true)}>Confirmar y lanzar</button><button className="btn" onClick={() => { setConfirmar(null); setConfirmo(false) }}>Cancelar</button></div>
            </div>
          )}
        </aside>
      </div>
    </>
  )
}
