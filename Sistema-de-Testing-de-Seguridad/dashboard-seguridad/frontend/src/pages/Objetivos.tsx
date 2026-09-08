import { useEffect, useState } from 'react'
import { ApiError, api, type ObjetivoRegistrado, type ResultadoPrueba } from '../api'
import { useCarga } from '../components/comunes'

type Tipo = 'http' | 'agente' | 'guardrail' | 'simulado'
interface Form {
  nombre: string; tipo: Tipo; descripcion: string; proposito: string
  url: string; metodo: string; cuerpo: string; ruta_respuesta: string; codigos_bloqueo: string; env_token: string; plantilla_auth: string; cabeceras: string
  ruta_proyecto: string; modulo: string; funcion: string; param_sesion: string; formato_sesion: string
  con_guardrail: boolean; g_modulo: string; g_funcion: string; g_evaluar_llm_siempre: boolean
  modo: string
}
const VACIO: Form = {
  nombre: '', tipo: 'http', descripcion: '', proposito: '',
  url: '', metodo: 'POST', cuerpo: '{\n  "mensaje": "{payload}",\n  "session_id": "{session_id}"\n}', ruta_respuesta: 'respuesta', codigos_bloqueo: '403, 422', env_token: '', plantilla_auth: 'Bearer {token}', cabeceras: '',
  ruta_proyecto: '', modulo: '', funcion: '', param_sesion: '', formato_sesion: 'uuid',
  con_guardrail: false, g_modulo: 'guardrails.input_guardrail', g_funcion: 'verificar_input_guardrail', g_evaluar_llm_siempre: true,
  modo: 'realista',
}

function desdeRegistro(o: ObjetivoRegistrado): Form {
  const c = o.config as Record<string, unknown>
  const g = (c.guardrail ?? null) as Record<string, unknown> | null
  return {
    ...VACIO, nombre: o.nombre, tipo: o.tipo as Tipo, descripcion: o.descripcion, proposito: o.proposito,
    url: String(c.url ?? ''), metodo: String(c.metodo ?? 'POST'), cuerpo: c.cuerpo ? JSON.stringify(c.cuerpo, null, 2) : VACIO.cuerpo,
    ruta_respuesta: String(c.ruta_respuesta ?? 'respuesta'), codigos_bloqueo: Array.isArray(c.codigos_bloqueo) ? (c.codigos_bloqueo as number[]).join(', ') : '403',
    env_token: String(c.env_token ?? ''), plantilla_auth: String(c.plantilla_auth ?? 'Bearer {token}'), cabeceras: c.cabeceras && Object.keys(c.cabeceras as object).length ? JSON.stringify(c.cabeceras, null, 2) : '',
    ruta_proyecto: String(c.ruta_proyecto ?? ''), modulo: String(c.modulo ?? ''), funcion: String(c.funcion ?? ''), param_sesion: String(c.param_sesion ?? ''), formato_sesion: String(c.formato_sesion ?? 'uuid'),
    con_guardrail: !!g, g_modulo: String(g?.modulo ?? 'guardrails.input_guardrail'), g_funcion: String(g?.funcion ?? 'verificar_input_guardrail'), g_evaluar_llm_siempre: g ? !!g.evaluar_llm_siempre : true,
    modo: String(c.modo ?? 'realista'),
  }
}

function aConfig(f: Form): Record<string, unknown> {
  const base = { tipo: f.tipo, descripcion: f.descripcion, proposito: f.proposito }
  if (f.tipo === 'http') return { ...base, url: f.url, metodo: f.metodo, cuerpo: f.cuerpo, ruta_respuesta: f.ruta_respuesta, codigos_bloqueo: f.codigos_bloqueo, env_token: f.env_token, plantilla_auth: f.plantilla_auth, cabeceras: f.cabeceras }
  if (f.tipo === 'agente') return { ...base, ruta_proyecto: f.ruta_proyecto, modulo: f.modulo, funcion: f.funcion, param_sesion: f.param_sesion, formato_sesion: f.formato_sesion, guardrail: f.con_guardrail ? { modulo: f.g_modulo, funcion: f.g_funcion, evaluar_llm_siempre: f.g_evaluar_llm_siempre } : null }
  if (f.tipo === 'guardrail') return { ...base, ruta_proyecto: f.ruta_proyecto, modulo: f.modulo, funcion: f.funcion }
  return { ...base, modo: f.modo }
}

const TIPOS: { id: Tipo; nombre: string; desc: string }[] = [
  { id: 'http', nombre: 'Endpoint HTTP', desc: 'Un agente desplegado detrás de una URL (FastAPI, n8n, cualquier API). No hace falta el código. Es el caso normal en el equipo.' },
  { id: 'agente', nombre: 'Agente Python', desc: 'Un agente importable desde este servidor: ruta del proyecto, módulo y función texto→texto. Permite medir el guardrail y el LLM por separado.' },
  { id: 'guardrail', nombre: 'Solo guardrail', desc: 'Solo el filtro de entrada de un proyecto Python. Rápido y gratis; sirve para Red Turing, no para DeepTeam.' },
  { id: 'simulado', nombre: 'Simulado', desc: 'Objetivo de mentira para verificar que el arnés detecta. Sin coste.' },
]

export default function Objetivos() {
  const { datos, error, recargar } = useCarga(() => api.get<ObjetivoRegistrado[]>('/api/objetivos'), [])
  const [f, setF] = useState<Form | null>(null)
  const [original, setOriginal] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ tipo: 'ok' | 'error'; texto: string } | null>(null)
  const [prueba, setPrueba] = useState<{ nombre: string; res?: ResultadoPrueba; cargando: boolean } | null>(null)
  useEffect(() => { setMsg(null) }, [f?.nombre, f?.tipo])

  async function guardar() {
    if (!f) return
    try {
      await api.post('/api/objetivos', { nombre: f.nombre.trim(), config: aConfig(f), renombrar_desde: original })
      setMsg({ tipo: 'ok', texto: `Objetivo «${f.nombre}» guardado en targets.yaml. Ya aparece en Red Turing y DeepTeam.` }); setOriginal(f.nombre); recargar()
    } catch (e) { setMsg({ tipo: 'error', texto: (e as ApiError).message }) }
  }
  async function eliminar(nombre: string) {
    if (!confirm(`¿Eliminar el objetivo «${nombre}» de targets.yaml? Los informes ya generados no se borran.`)) return
    try { await api.delete(`/api/objetivos/${encodeURIComponent(nombre)}`); setF(null); setOriginal(null); recargar() } catch (e) { setMsg({ tipo: 'error', texto: (e as ApiError).message }) }
  }
  async function probar(nombre: string) {
    setPrueba({ nombre, cargando: true })
    try { const res = await api.post<ResultadoPrueba>(`/api/objetivos/${encodeURIComponent(nombre)}/probar`, {}); setPrueba({ nombre, res, cargando: false }) }
    catch (e) { setPrueba({ nombre, res: { ok: false, fase: 'peticion', error: (e as ApiError).message, latencia_ms: 0 }, cargando: false }) }
  }

  if (error) return <div className="error">{error}</div>
  return (
    <>
      <header className="cab">
        <h2>Objetivos</h2><span className="etq">compartidos por Red Turing y DeepTeam</span>
        <span className="meta">Los agentes que se van a probar. Se guardan en <code>Red-Turing/targets.yaml</code>.</span>
        <div className="derecha"><button className="btn btn-neutro" onClick={() => { setF({ ...VACIO }); setOriginal(null) }}>＋ Registrar objetivo</button></div>
      </header>

      <div className="form-grid">
        <div>
          {(datos ?? []).map(o => (
            <div key={o.nombre} className={`vuln ${f?.nombre === o.nombre ? 'on' : ''}`} style={{ padding: '10px 12px' }}>
              <div className="cab-v" onClick={() => { setF(desdeRegistro(o)); setOriginal(o.nombre); setPrueba(null) }}>
                <b className="mono">{o.nombre}</b><span className={`etq ${o.tipo === 'http' ? 'dt' : ''}`}>{o.tipo}</span>
                <span className="d">{o.descripcion || o.destino}</span>
                {o.con_coste ? <span className="etq rojo">cuesta</span> : <span className="etq">gratis</span>}
                {!o.sirve_para_deepteam && <span className="etq" title="No devuelve texto">solo Red Turing</span>}
              </div>
              <div className="acciones" style={{ marginTop: 6 }}>
                <button className="btn chico" onClick={() => probar(o.nombre)} disabled={prueba?.cargando}>{prueba?.nombre === o.nombre && prueba.cargando ? 'Probando…' : 'Probar conexión'}</button>
                <span className="nota" style={{ padding: 0 }}>{o.destino}</span>
              </div>
              {prueba?.nombre === o.nombre && prueba.res && (
                <div className={prueba.res.ok ? 'aviso' : 'error'} style={{ marginTop: 8 }}>
                  {prueba.res.ok ? <>
                    <b>Responde</b> en {prueba.res.latencia_ms} ms{prueba.res.bloqueado ? <> · el guardrail <b>bloqueó</b> el saludo ({prueba.res.capa})</> : ''}
                    {prueba.res.texto && <pre style={{ margin: '6px 0 0', whiteSpace: 'pre-wrap', fontSize: 12 }}>{prueba.res.texto}</pre>}
                  </> : <><b>No responde</b> ({prueba.res.fase}): {prueba.res.error}</>}
                </div>
              )}
            </div>
          ))}
          {datos && !datos.length && <div className="nota">No hay objetivos. Registra el primero.</div>}
        </div>

        <aside className="panel">
          {!f ? <div className="nota">Elige un objetivo para editarlo o registra uno nuevo. Para un agente desplegado solo necesitas su URL y saber cómo espera el mensaje y dónde devuelve la respuesta.</div> : (
            <>
              <h3>{original ? `Editar «${original}»` : 'Nuevo objetivo'}</h3>
              <div className="campo"><label>Nombre (identificador)</label><input type="text" value={f.nombre} placeholder="p. ej. asistente-ventas-prod" onChange={e => setF({ ...f, nombre: e.target.value.toLowerCase() })} /><div className="ayuda">Minúsculas, dígitos y guiones. Es el nombre que verás en ambos motores.</div></div>
              <div className="campo"><span className="rot">Tipo</span>
                <div className="chips">{TIPOS.map(t => <button key={t.id} type="button" className={`chip ${f.tipo === t.id ? 'on' : ''}`} onClick={() => setF({ ...f, tipo: t.id })}>{t.nombre}</button>)}</div>
                <div className="ayuda">{TIPOS.find(t => t.id === f.tipo)?.desc}</div>
              </div>
              <div className="campo"><label>Descripción</label><input type="text" value={f.descripcion} placeholder="Qué agente es y dónde vive" onChange={e => setF({ ...f, descripcion: e.target.value })} /></div>

              {f.tipo === 'http' && <>
                <div className="doble">
                  <div className="campo" style={{ gridColumn: '1 / span 2' }}><label>URL del endpoint</label><input type="text" value={f.url} placeholder="https://mi-agente.empresa.com/chat" onChange={e => setF({ ...f, url: e.target.value })} /></div>
                </div>
                <div className="doble">
                  <div className="campo"><label>Método</label><select value={f.metodo} onChange={e => setF({ ...f, metodo: e.target.value })}><option>POST</option><option>PUT</option><option>GET</option></select></div>
                  <div className="campo"><label>Ruta de la respuesta en el JSON</label><input type="text" value={f.ruta_respuesta} onChange={e => setF({ ...f, ruta_respuesta: e.target.value })} /><div className="ayuda">Con puntos: <code>respuesta</code>, <code>data.mensaje</code>, <code>choices.0.message.content</code>.</div></div>
                </div>
                <div className="campo"><label>Cuerpo de la petición (JSON)</label><textarea value={f.cuerpo} onChange={e => setF({ ...f, cuerpo: e.target.value })} style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }} /><div className="ayuda"><code>{'{payload}'}</code> se sustituye por el ataque. <code>{'{session_id}'}</code> por un UUID nuevo en cada caso (y el mismo durante un ataque multi-turno).</div></div>
                <div className="doble">
                  <div className="campo"><label>Códigos HTTP que significan «bloqueado»</label><input type="text" value={f.codigos_bloqueo} onChange={e => setF({ ...f, codigos_bloqueo: e.target.value })} /><div className="ayuda">Si tu API responde 403 o 422 cuando su guardrail para el mensaje.</div></div>
                  <div className="campo"><label>Variable de entorno con el token</label><input type="text" value={f.env_token} placeholder="RT_TOKEN_MI_AGENTE" onChange={e => setF({ ...f, env_token: e.target.value.toUpperCase() })} /><div className="ayuda">Solo el NOMBRE. El valor va en el entorno del servidor, nunca aquí.</div></div>
                </div>
                {f.env_token && <div className="campo"><label>Plantilla de autorización</label><input type="text" value={f.plantilla_auth} onChange={e => setF({ ...f, plantilla_auth: e.target.value })} /><div className="ayuda">Se envía como cabecera Authorization. <code>{'{token}'}</code> es el valor de la variable.</div></div>}
                <div className="campo"><label>Otras cabeceras (JSON, opcional)</label><textarea value={f.cabeceras} placeholder='{"X-Cliente": "redteam"}' onChange={e => setF({ ...f, cabeceras: e.target.value })} style={{ minHeight: 56, fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }} /></div>
              </>}

              {(f.tipo === 'agente' || f.tipo === 'guardrail') && <>
                <div className="campo"><label>Carpeta del proyecto Python</label><input type="text" value={f.ruta_proyecto} placeholder="../MiAgente  o  /ruta/absoluta" onChange={e => setF({ ...f, ruta_proyecto: e.target.value })} /><div className="ayuda">Relativa a la carpeta de Red Turing o absoluta. Se importa desde este servidor, así que sus dependencias deben estar en el mismo entorno.</div></div>
                <div className="doble">
                  <div className="campo"><label>Módulo</label><input type="text" value={f.modulo} placeholder={f.tipo === 'agente' ? 'agente_sec_langfuse' : 'guardrails.input_guardrail'} onChange={e => setF({ ...f, modulo: e.target.value })} /></div>
                  <div className="campo"><label>Función</label><input type="text" value={f.funcion} placeholder={f.tipo === 'agente' ? 'chat_con_agente' : 'verificar_input_guardrail'} onChange={e => setF({ ...f, funcion: e.target.value })} /><div className="ayuda">{f.tipo === 'agente' ? 'Recibe el mensaje y devuelve texto.' : 'Devuelve (es_seguro, motivo).'}</div></div>
                </div>
                {f.tipo === 'agente' && <>
                  <div className="doble">
                    <div className="campo"><label>Parámetro de sesión</label><input type="text" value={f.param_sesion} placeholder="auto (session_id, thread_id…)" onChange={e => setF({ ...f, param_sesion: e.target.value })} /></div>
                    <div className="campo"><label>Formato de sesión</label><select value={f.formato_sesion} onChange={e => setF({ ...f, formato_sesion: e.target.value })}><option value="uuid">UUID</option><option value="prefijo">prefijo redturing-…</option></select></div>
                  </div>
                  <label className="check"><input type="checkbox" checked={f.con_guardrail} onChange={e => setF({ ...f, con_guardrail: e.target.checked })} /><span>Declarar el guardrail del agente<span className="ayuda">Permite atribuir la capa que bloqueó y medir el LLM por separado (modo «solo LLM») en ambos motores.</span></span></label>
                  {f.con_guardrail && <>
                    <div className="doble">
                      <div className="campo"><label>Módulo del guardrail</label><input type="text" value={f.g_modulo} onChange={e => setF({ ...f, g_modulo: e.target.value })} /></div>
                      <div className="campo"><label>Función</label><input type="text" value={f.g_funcion} onChange={e => setF({ ...f, g_funcion: e.target.value })} /></div>
                    </div>
                    <label className="check"><input type="checkbox" checked={f.g_evaluar_llm_siempre} onChange={e => setF({ ...f, g_evaluar_llm_siempre: e.target.checked })} /><span>Red Turing: enviar al LLM también lo que el guardrail bloquea<span className="ayuda">Da el «ASR solo LLM». Cuesta una llamada al modelo por caso.</span></span></label>
                  </>}
                </>}
              </>}

              {f.tipo === 'simulado' && <div className="campo"><label>Modo</label><select value={f.modo} onChange={e => setF({ ...f, modo: e.target.value })}><option value="vulnerable">vulnerable (obedece todo)</option><option value="blindado">blindado (bloquea todo)</option><option value="realista">realista</option></select></div>}

              {f.tipo !== 'guardrail' && <div className="campo"><label>Propósito (para DeepTeam)</label><textarea value={f.proposito} placeholder="Qué hace el agente, para quién, qué herramientas y datos tiene, en qué idioma responde. El adversario lo usa para inventar ataques creíbles." onChange={e => setF({ ...f, proposito: e.target.value })} /></div>}

              {msg && <div className={msg.tipo === 'ok' ? 'aviso' : 'error'}>{msg.texto}</div>}
              <div className="acciones">
                <button className="btn btn-neutro" onClick={guardar} disabled={!f.nombre.trim()}>Guardar</button>
                {original && <button className="btn chico" onClick={() => probar(original)}>Probar conexión</button>}
                {original && <button className="btn chico" style={{ color: 'var(--critico-ink)' }} onClick={() => eliminar(original)}>Eliminar</button>}
                <button className="btn chico" onClick={() => { setF(null); setOriginal(null) }}>Cerrar</button>
              </div>
            </>
          )}
        </aside>
      </div>
    </>
  )
}
