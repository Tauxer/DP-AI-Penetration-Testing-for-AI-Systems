import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api, type Ataque, type Catalogo, type ConfigDT, type EstadoDT } from '../api'
import { useCarga } from '../components/comunes'

interface Estimacion { casos: number; llamadas_agente_min: number; llamadas_agente_max: number; llamadas_adversario_aprox: number; llamadas_juez: number; incluye_multi_turno: boolean }

function SelectorModelo({ rot, ayuda, valor, onChange, modelos }: { rot: string; ayuda: string; valor: string; onChange: (v: string) => void; modelos: Catalogo['modelos'] }) {
  const preset = modelos.find(m => m.id === valor)
  const [otro, setOtro] = useState(!preset)
  return (
    <div className="campo">
      <label>{rot}</label>
      <div className="modelo">
        {otro ? <input type="text" value={valor} placeholder="nombre del modelo de OpenAI" onChange={e => onChange(e.target.value)} />
          : <select value={valor} onChange={e => onChange(e.target.value)}>{modelos.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}</select>}
        <button type="button" className="btn chico" onClick={() => setOtro(!otro)}>{otro ? 'Lista' : 'Otro…'}</button>
        <div className="nota">{preset?.nota ?? ayuda}</div>
      </div>
    </div>
  )
}

// Cada método de ataque se muestra como tarjeta en una rejilla de tres columnas,
// con la mecánica y para qué sirve, porque el nombre solo (SyntheticContextInjection,
// BadLikertJudge…) no dice a quién le conviene elegirlo.
function TarjetaAtaque({ a, on, onClick }: { a: Ataque; on: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`metodo ${on ? 'on' : ''}`} aria-pressed={on} onClick={onClick}>
      <span className="cab-m">
        <b>{a.nombre}</b>
        {a.recomendado && <span className="etq dt">recomendado</span>}
        {!a.usa_llm && <span className="etq">sin LLM</span>}
        {a.multi_turno && <span className="etq rojo">×5 turnos</span>}
      </span>
      <span className="q">{a.descripcion}</span>
      <span className="p">{a.para_que}</span>
    </button>
  )
}

export default function DeepTeamNueva() {
  const nav = useNavigate()
  const { datos: cat, error: errCat } = useCarga(() => api.get<Catalogo>('/api/deepteam/catalogo'), [])
  const [cfg, setCfg] = useState<ConfigDT | null>(null)
  const [vulns, setVulns] = useState<Record<string, Set<string>>>({})
  const [ataques, setAtaques] = useState<Set<string>>(new Set())
  const [porTipo, setPorTipo] = useState(1)
  const [conGuardrail, setConGuardrail] = useState(true)
  const [etiqueta, setEtiqueta] = useState('')
  const [objetivo, setObjetivo] = useState('')
  const [propositoTocado, setPropositoTocado] = useState(false)
  const [verTodas, setVerTodas] = useState(false)
  const [est, setEst] = useState<Estimacion | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmar, setConfirmar] = useState(false)
  const [confirmo, setConfirmo] = useState(false)
  const [guardado, setGuardado] = useState('')

  useEffect(() => {
    if (!cat) return
    setCfg(cat.config); setPorTipo(cat.config.ataques_por_tipo)
    const utiles = cat.objetivos.filter(o => o.sirve_para_deepteam)
    const ini = utiles.find(o => o.nombre === cat.config.objetivo_por_defecto) ?? utiles.find(o => o.tipo !== 'simulado') ?? utiles[0]
    if (ini) { setObjetivo(ini.nombre); if (ini.proposito) setCfg(c => c && ({ ...c, proposito: ini.proposito })) }
    // Selección inicial: dos vulnerabilidades y dos ataques recomendados, con todos sus tipos.
    const iniVulns: Record<string, Set<string>> = {}
    for (const v of cat.vulnerabilidades.filter(x => ['PromptLeakage', 'PIILeakage'].includes(x.nombre))) iniVulns[v.nombre] = new Set(v.tipos)
    setVulns(iniVulns); setAtaques(new Set(['PromptInjection', 'Roleplay']))
  }, [cat])

  const objSel = cat?.objetivos.find(o => o.nombre === objetivo)
  useEffect(() => { if (objSel && !propositoTocado) setCfg(c => c && ({ ...c, proposito: objSel.proposito || cat!.config.proposito })) }, [objSel, propositoTocado]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (objSel && !objSel.permite_solo_llm) setConGuardrail(true) }, [objSel])

  const peticion = useMemo(() => cfg && objetivo && ({
    objetivo,
    vulnerabilidades: Object.entries(vulns).map(([nombre, tipos]) => ({ nombre, tipos: [...tipos] })),
    ataques: [...ataques], modelo_adversario: cfg.modelo_adversario, modelo_juez: cfg.modelo_juez, en_espanol: cfg.en_espanol,
    ataques_por_tipo: porTipo, con_guardrail: conGuardrail, max_concurrentes: cfg.max_concurrentes, proposito: cfg.proposito, etiqueta,
  }), [cfg, objetivo, vulns, ataques, porTipo, conGuardrail, etiqueta])

  useEffect(() => {
    if (!peticion || !peticion.vulnerabilidades.length || !peticion.ataques.length) { setEst(null); return }
    const t = setTimeout(() => api.post<Estimacion>('/api/deepteam/estimar', peticion).then(e => { setEst(e); setError(null) }).catch(e => { setEst(null); setError(e.message) }), 200)
    return () => clearTimeout(t)
  }, [peticion])

  if (errCat) return <div className="error">No se pudo cargar el catálogo de DeepTeam: {errCat}</div>
  if (!cat || !cfg) return <div className="nota">Cargando catálogo de DeepTeam…</div>

  const toggleVuln = (nombre: string, tipos: string[]) => setVulns(v => { const n = { ...v }; if (n[nombre]) delete n[nombre]; else n[nombre] = new Set(tipos); return n })
  const toggleTipo = (nombre: string, tipo: string, todos: string[]) => setVulns(v => { const n = { ...v }; const s = new Set(n[nombre] ?? todos); s.has(tipo) ? s.delete(tipo) : s.add(tipo); if (s.size) n[nombre] = s; else delete n[nombre]; return n })
  const toggleAtaque = (a: string) => setAtaques(s => { const n = new Set(s); n.has(a) ? n.delete(a) : n.add(a); return n })
  const listaVulns = verTodas ? cat.vulnerabilidades : cat.vulnerabilidades.filter(v => v.recomendada || vulns[v.nombre])

  async function guardarDefecto() {
    const c = await api.put<ConfigDT>('/api/deepteam/config', { modelo_adversario: cfg!.modelo_adversario, modelo_juez: cfg!.modelo_juez, en_espanol: cfg!.en_espanol, ataques_por_tipo: porTipo, max_concurrentes: cfg!.max_concurrentes, proposito: cfg!.proposito })
    setCfg(c); setGuardado('Guardado como valores por defecto.'); setTimeout(() => setGuardado(''), 2500)
  }
  async function lanzar() {
    setError(null)
    try { await api.post<EstadoDT>('/api/deepteam/evaluar', { ...peticion, confirmar: true }); nav('/deepteam/estado') }
    catch (e) { const err = e as ApiError; if (err.estado === 409) { nav('/deepteam/estado'); return } setError(err.message) }
  }

  return (
    <>
      <header className="cab"><h2>Nueva evaluación</h2><span className="etq dt">DeepTeam</span><span className="meta">Un LLM adversario inventa los ataques a partir del propósito del agente; otro LLM juzga si cedió.</span></header>
      <div className="form-grid">
        <div>
          <section className="panel">
            <h3>Objetivo</h3><p className="desc">El agente que se va a atacar. Se registra en la sección Objetivos; aquí solo se elige.</p>
            <div className="campo">
              <select value={objetivo} onChange={e => setObjetivo(e.target.value)}>
                {cat.objetivos.filter(o => o.sirve_para_deepteam).map(o => <option key={o.nombre} value={o.nombre}>{o.nombre} · {o.tipo}{o.descripcion ? ` · ${o.descripcion}` : ''}</option>)}
              </select>
              {objSel && <div className="ayuda">{objSel.con_coste ? <span className="etq rojo">CUESTA</span> : <span className="etq">GRATIS</span>} {objSel.tipo === 'http' ? 'Agente desplegado: cada caso es una petición HTTP real.' : objSel.tipo === 'agente' ? 'Agente Python importado en este servidor.' : 'Objetivo simulado: sin coste.'} <code>{objSel.destino}</code></div>}
              {!cat.objetivos.some(o => o.sirve_para_deepteam) && <div className="error">No hay objetivos que devuelvan texto. Registra uno en Objetivos.</div>}
            </div>
          </section>

          <section className="panel">
            <h3>Modelos</h3><p className="desc">Los dos se pagan con tu clave de OpenAI. El agente atacado usa su propio modelo por su cuenta.</p>
            <div className="doble">
              <SelectorModelo rot="Modelo adversario" ayuda="Genera y reescribe los payloads (DeepTeam lo llama simulator)." valor={cfg.modelo_adversario} onChange={v => setCfg({ ...cfg, modelo_adversario: v })} modelos={cat.modelos} />
              <SelectorModelo rot="Modelo juez" ayuda="Evalúa cada respuesta de TramiBot con 0 o 1 y una razón." valor={cfg.modelo_juez} onChange={v => setCfg({ ...cfg, modelo_juez: v })} modelos={cat.modelos} />
            </div>
            <label className="check"><input type="checkbox" checked={cfg.en_espanol} onChange={e => setCfg({ ...cfg, en_espanol: e.target.checked })} /><span>Ataques en español<span className="ayuda">DeepTeam reescribe en inglés al "mejorar" cada ataque; esto lo devuelve al español con el mismo modelo adversario. Los multi-turno no se traducen.</span></span></label>
            <div className="acciones"><button className="btn chico" onClick={guardarDefecto}>Guardar como valores por defecto</button><span className="nota" style={{ padding: 0 }}>{guardado}</span></div>
          </section>

          <section className="panel">
            <h3>Vulnerabilidades</h3><p className="desc">Qué debilidad busca el adversario. Cada tipo genera sus propios casos. <button className="btn chico" onClick={() => setVerTodas(!verTodas)}>{verTodas ? 'Solo recomendadas' : `Ver las ${cat.vulnerabilidades.length}`}</button></p>
            <div className="vulns">{listaVulns.map(v => {
              const on = !!vulns[v.nombre]
              return (
                // Los chips de tipo quedan FUERA del <label>: dentro, cada clic en un
                // tipo alternaría además la casilla de la vulnerabilidad entera.
                <div key={v.nombre} className={`vuln ${on ? 'on' : ''}`}>
                  <label className="cab-v">
                    <input type="checkbox" checked={on} onChange={() => toggleVuln(v.nombre, v.tipos)} />
                    <span className="nom"><b>{v.nombre}</b>{v.contenido_daniino && <span className="etq rojo" title="Genera contenido dañino real; quedará en los JSON y en Langfuse">dañino</span>}</span>
                    <span className="d">{v.descripcion}</span>
                  </label>
                  {on && <div className="tipos">{v.tipos.map(t => <button key={t} type="button" className={`chip dt ${vulns[v.nombre]?.has(t) ? 'on' : ''}`} onClick={() => toggleTipo(v.nombre, t, v.tipos)}>{t}</button>)}</div>}
                </div>
              )
            })}</div>
          </section>

          <section className="panel">
            <h3>Métodos de ataque</h3><p className="desc">Cómo disfraza el adversario cada petición. Los multi-turno mantienen una conversación con TramiBot y cuestan varias llamadas por caso.</p>
            <div className="metodos">{cat.ataques.filter(a => !a.multi_turno).map(a => <TarjetaAtaque key={a.nombre} a={a} on={ataques.has(a.nombre)} onClick={() => toggleAtaque(a.nombre)} />)}</div>
            <span className="rot sep-metodos">Multi-turno<span className="ayuda">Mantienen una conversación de varios turnos con el agente: son los más eficaces y los más caros.</span></span>
            <div className="metodos">{cat.ataques.filter(a => a.multi_turno).map(a => <TarjetaAtaque key={a.nombre} a={a} on={ataques.has(a.nombre)} onClick={() => toggleAtaque(a.nombre)} />)}</div>
          </section>

          <section className="panel">
            <h3>Objetivo y alcance</h3>
            <div className="doble">
              <div className="campo"><label>Ataques por tipo de vulnerabilidad</label><input type="number" min={1} max={10} value={porTipo} onChange={e => setPorTipo(Math.min(10, Math.max(1, +e.target.value || 1)))} /></div>
              <div className="campo"><label>Etiqueta (opcional)</label><input type="text" value={etiqueta} placeholder="p. ej. juez gpt-4.1 vs gpt-4o-mini" onChange={e => setEtiqueta(e.target.value)} /></div>
            </div>
            <div className="campo"><span className="rot">Qué se ataca</span>
              <div className="seg"><button className={conGuardrail ? 'on' : ''} onClick={() => setConGuardrail(true)}>Sistema completo (guardrail + LLM)</button><button className={!conGuardrail ? 'on' : ''} disabled={!objSel?.permite_solo_llm} onClick={() => setConGuardrail(false)}>Solo LLM (guardrail neutralizado)</button></div>
              <div className="ayuda">{objSel?.permite_solo_llm ? 'Igual que en Red Turing: "solo LLM" mide el modelo y su system prompt sin el filtro delante.' : 'Solo LLM requiere un objetivo tipo agente con su guardrail declarado; un endpoint HTTP se prueba siempre completo.'}</div>
            </div>
            <div className="campo"><label>Propósito del objetivo (lo que el adversario sabe de TramiBot)</label><textarea value={cfg.proposito} onChange={e => { setPropositoTocado(true); setCfg({ ...cfg, proposito: e.target.value }) }} /><div className="ayuda">Se rellena con el propósito guardado en el objetivo. Puedes ajustarlo solo para esta evaluación.</div></div>
          </section>
        </div>

        <aside className="panel plan">
          <h3>Qué se va a lanzar</h3><p className="desc">Estimación; los multi-turno pueden variar.</p>
          {est ? (
            <>
              <div className="grande">{est.casos}<small>casos</small></div>
              <div className="sub">{Object.keys(vulns).length} vulnerabilidades · {ataques.size} métodos · {porTipo} por tipo</div>
              <dl className="kv">
                <dt>Llamadas al agente</dt><dd>{est.llamadas_agente_min}{est.llamadas_agente_max > est.llamadas_agente_min ? ` – ${est.llamadas_agente_max}` : ''}</dd>
                <dt>Llamadas al adversario</dt><dd>≈ {est.llamadas_adversario_aprox} · <code>{cfg.modelo_adversario}</code></dd>
                <dt>Llamadas al juez</dt><dd>{est.llamadas_juez} · <code>{cfg.modelo_juez}</code></dd>
              </dl>
              <div className="coste">Todo son llamadas reales con tu clave de OpenAI y quedarán trazas en Langfuse. Referencia: 5 casos con gpt-4o-mini costaron ≈ $0.15 de DeepTeam más TramiBot.</div>
            </>
          ) : <div className="nota">Elige al menos una vulnerabilidad y un método.</div>}
          {error && <div className="error">{error}</div>}
          {!confirmar ? <div className="acciones"><button className="btn btn-dt" disabled={!est} onClick={() => setConfirmar(true)}>Lanzar evaluación</button></div> : (
            <div className="confirmar">
              <h4>Confirmar gasto</h4>
              <p>Adversario <b>{cfg.modelo_adversario}</b>, juez <b>{cfg.modelo_juez}</b>, {est?.casos} casos contra <code>{objetivo}</code> en modo <b>{conGuardrail ? 'sistema completo' : 'solo LLM'}</b>.</p>
              <label className="check"><input type="checkbox" checked={confirmo} onChange={e => setConfirmo(e.target.checked)} /><span>Entiendo el coste y que los resultados quedan en local.</span></label>
              <div className="acciones"><button className="btn btn-dt" disabled={!confirmo} onClick={lanzar}>Confirmar y lanzar</button><button className="btn" onClick={() => { setConfirmar(false); setConfirmo(false) }}>Cancelar</button></div>
            </div>
          )}
        </aside>
      </div>
    </>
  )
}
