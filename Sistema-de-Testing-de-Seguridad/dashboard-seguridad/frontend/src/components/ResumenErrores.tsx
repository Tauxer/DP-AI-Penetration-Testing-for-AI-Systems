import type { ResumenDT } from '../api'

const CULPABLE: Record<string, { etq: string; expl: string }> = {
  adversario: { etq: 'adversario', expl: 'El modelo adversario no consiguió generar el ataque. No dice nada de tu agente; suele pasar con gpt-4.1 como adversario. Prueba gpt-4o-mini.' },
  juez: { etq: 'juez', expl: 'El modelo juez no pudo emitir veredicto.' },
  agente: { etq: 'agente', expl: 'Tu agente no respondió (timeout, error HTTP, excepción). Revisa la terminal donde corre.' },
}

/** Conteos y errores de una evaluación terminada. Se usa en la pantalla de estado y en el detalle. */
export default function ResumenErrores({ r, compacto }: { r: ResumenDT; compacto?: boolean }) {
  const porCulpable = new Map<string, number>()
  for (const e of r.errores_detalle) porCulpable.set(e.culpable, (porCulpable.get(e.culpable) ?? 0) + 1)
  return (
    <section className="panel">
      <h3>Resultado</h3>
      <p className="desc">{r.total} casos · <span className="res-con">{r.aguantaron} aguantó</span> · <span className={r.cedieron ? 'res-pen' : ''}>{r.cedieron} cedió</span> · <span className={r.errores ? 'res-rev' : ''}>{r.errores} con error</span></p>
      {r.errores > 0 ? (
        <>
          <div className="aviso" style={{ marginTop: 0 }}>
            <b>DeepTeam tuvo {r.errores} {r.errores === 1 ? 'error' : 'errores'}.</b> Los casos con error no cuentan ni como aguantó ni como cedió.
            {[...porCulpable.entries()].map(([k, n]) => <div key={k} style={{ marginTop: 4 }}><span className="etq">{CULPABLE[k]?.etq ?? k} · {n}</span> {CULPABLE[k]?.expl}</div>)}
          </div>
          <div className="scroll"><table>
            <thead><tr><th>Vulnerabilidad</th><th>Tipo</th><th>Método</th><th>Quién falló</th><th>Error</th></tr></thead>
            <tbody>{r.errores_detalle.map((e, i) => <tr key={i}><td>{e.vulnerabilidad}</td><td className="mono">{e.tipo ?? '—'}</td><td>{e.ataque ?? <span className="mudo">no llegó a elegirse</span>}</td><td><span className="etq">{e.culpable}</span></td><td style={{ fontSize: 12, color: 'var(--texto-2)' }}>{e.error}</td></tr>)}</tbody>
          </table></div>
        </>
      ) : <div className="aviso" style={{ marginTop: 0 }}>DeepTeam no tuvo errores: los {r.total} casos se generaron, se enviaron y se juzgaron.</div>}
      {!compacto && r.cedieron > 0 && (
        <>
          <h4 style={{ margin: '14px 0 6px', fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--texto-3)' }}>Casos en que el juez vio ceder al agente</h4>
          <div className="scroll"><table>
            <thead><tr><th>Vulnerabilidad</th><th>Tipo</th><th>Método</th><th>Razón del juez</th></tr></thead>
            <tbody>{r.cedieron_detalle.map((c, i) => <tr key={i}><td>{c.vulnerabilidad}</td><td className="mono">{c.tipo ?? '—'}</td><td>{c.ataque}</td><td style={{ fontSize: 12, color: 'var(--texto-2)' }}>{c.razon}</td></tr>)}</tbody>
          </table></div>
        </>
      )}
    </section>
  )
}
