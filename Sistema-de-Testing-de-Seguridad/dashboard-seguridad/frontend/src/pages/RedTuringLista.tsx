import { Link } from 'react-router-dom'
import { api, type CorridaResumen } from '../api'
import { estadoAsr, fecha, pct, useCarga } from '../components/comunes'

export default function RedTuringLista() {
  const { datos, error, cargando } = useCarga(() => api.get<CorridaResumen[]>('/api/redturing/corridas'), [])
  if (error) return <div className="error">No se pudo leer reports/: {error}</div>
  if (cargando || !datos) return <div className="nota">Cargando…</div>

  const grupos = new Map<string, CorridaResumen[]>()
  for (const c of datos) grupos.set(c.objetivo, [...(grupos.get(c.objetivo) ?? []), c])

  return (
    <>
      <header className="cab">
        <h2>Corridas de Red Turing</h2>
        <span className="etq rt">corpus fijo · determinístico</span>
        <span className="meta">{datos.length} informes en reports/</span>
        <div className="derecha"><Link className="btn btn-rt" to="/redturing/nueva">＋ Nueva corrida</Link></div>
      </header>
      {!datos.length && <div className="nota">Todavía no hay informes. Lanza tu primera corrida.</div>}
      {[...grupos.entries()].map(([obj, items]) => (
        <section className="grupo-t" key={obj}>
          <h3>{obj} <span className="etq">{items[0].tipo_objetivo}</span></h3>
          <div className="tarjetas">
            {items.map(c => {
              const e = estadoAsr(c.asr)
              return (
                <Link className="tarjeta" key={c.archivo} to={`/redturing/corrida/${encodeURIComponent(c.archivo)}`}>
                  <div className="t"><b>{fecha(c.inicio)}</b>{c.es_baseline && <span className="etq">baseline</span>}<span className={`cifra e-${e.c}`}>{pct(c.asr)}</span></div>
                  <div className="m">{c.exitosos}/{c.evaluados} penetraron{c.errores ? ` · ${c.errores} sin medir` : ''}{c.falsos_positivos !== null && c.falsos_positivos !== undefined ? ` · FP ${pct(c.falsos_positivos)}` : ''}</div>
                  <div className="m">{c.duracion_s}s · juez {c.juez_activo ? 'activo' : 'inactivo'}</div>
                </Link>
              )
            })}
          </div>
        </section>
      ))}
    </>
  )
}
