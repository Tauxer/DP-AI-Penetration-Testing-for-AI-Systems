import { Link } from 'react-router-dom'
import { api, type EvaluacionResumen } from '../api'
import { estadoAsr, fecha, pct, useCarga } from '../components/comunes'

export default function DeepTeamLista() {
  const { datos, error, cargando } = useCarga(() => api.get<EvaluacionResumen[]>('/api/deepteam/evaluaciones'), [])
  if (error) return <div className="error">No se pudieron leer las evaluaciones: {error}</div>
  if (cargando || !datos) return <div className="nota">Cargando…</div>
  return (
    <>
      <header className="cab">
        <h2>Evaluaciones de DeepTeam</h2><span className="etq dt">ataques generados por LLM · juez LLM</span>
        <span className="meta">{datos.length} evaluaciones en deepteam-pruebas/resultados/</span>
        <div className="derecha"><Link className="btn btn-dt" to="/deepteam/nueva">＋ Nueva evaluación</Link></div>
      </header>
      <div className="aviso">La <b>tasa de fallo</b> es la fracción de casos en que el juez consideró que TramiBot cedió. Lee siempre la razón del juez: se equivoca con los rechazos y no distingue un fail-close del guardrail.</div>
      {!datos.length && <div className="nota">Todavía no hay evaluaciones. Lanza la primera.</div>}
      <div className="tarjetas">
        {datos.map(ev => {
          const e = estadoAsr(ev.tasa_fallo)
          return (
            <Link className="tarjeta" key={ev.archivo} to={`/deepteam/evaluacion/${encodeURIComponent(ev.archivo)}`}>
              <div className="t"><b>{ev.etiqueta || fecha(ev.inicio)}</b><span className={`cifra e-${e.c}`}>{pct(ev.tasa_fallo)}</span></div>
              <div className="m">{ev.etiqueta && `${fecha(ev.inicio)} · `}{ev.fallidos}/{ev.evaluados} cedió{ev.errores ? ` · ${ev.errores} con error` : ''}{ev.cvss !== null && ev.cvss !== undefined ? ` · CVSS ${ev.cvss}` : ''}</div>
              <div className="m">{ev.objetivo ? <><code>{ev.objetivo}</code> · </> : ''}{ev.modo || 'modo no registrado'}</div>
              <div className="m">{ev.modelo_adversario ? <>adversario <code>{ev.modelo_adversario}</code> · juez <code>{ev.modelo_juez}</code></> : <span className="mudo">modelos no registrados (corrida desde script)</span>}</div>
            </Link>
          )
        })}
      </div>
    </>
  )
}
