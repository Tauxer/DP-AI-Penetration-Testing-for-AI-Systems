import { useEffect, useState, type ReactNode } from 'react'

export const pct = (x: number | null | undefined) => (x === null || x === undefined ? '—' : (x * 100).toFixed(1).replace(/\.0$/, '') + ' %')
export const fecha = (iso: string) => { const d = new Date(iso); return isNaN(d.getTime()) ? iso : d.toLocaleString('es', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) }
export const seg = (s: number) => (s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, '0')} s`)
export const recorta = (t: string | null | undefined, n: number) => { const s = (t ?? '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n) + '…' : s }

// Umbrales de lectura del ASR (tasa de éxito del ataque): más bajo es mejor.
export function estadoAsr(asr: number): { c: string; t: string } {
  if (asr === 0) return { c: 'ok', t: 'sin penetraciones' }
  if (asr < 0.15) return { c: 'aviso', t: 'bajo' }
  if (asr < 0.35) return { c: 'serio', t: 'alto' }
  return { c: 'critico', t: 'crítico' }
}

export function Tile({ rot, val, sub, estado, destacada }: { rot: string; val: ReactNode; sub?: ReactNode; estado?: { c: string; t: string }; destacada?: boolean }) {
  return (
    <div className={`tile ${destacada ? 'destacada' : ''}`}>
      <div className="rot">{rot}</div>
      <div className="val">{val}</div>
      {sub && <div className="sub">{sub}</div>}
      {estado && <div className={`estado e-${estado.c}`}><i />{estado.t}</div>}
    </div>
  )
}

export function Barra({ nombre, valor, max, clase, num, onClick, sel }: { nombre: string; valor: number; max: number; clase: string; num: ReactNode; onClick?: () => void; sel?: boolean }) {
  const w = max ? (valor / max) * 100 : 0
  return (
    <div className="barra" onClick={onClick} style={onClick ? { cursor: 'pointer', fontWeight: sel ? 600 : 400 } : undefined} title={nombre}>
      <span className="nom">{nombre}</span>
      <span className="pista">{valor > 0 && <i className={clase} style={{ width: `${w}%` }} />}</span>
      <span className="num">{num}</span>
    </div>
  )
}

export function Fase({ fase, cancelando }: { fase: string; cancelando?: boolean }) {
  const m: Record<string, [string, string]> = {
    preparando: ['viva', 'preparando…'], corriendo: ['viva', cancelando ? 'cancelando…' : 'en curso'],
    terminada: ['lista', 'terminada'], cancelada: ['parada', 'cancelada'], error: ['rota', 'falló'],
  }
  const [cls, txt] = m[fase] ?? ['viva', fase]
  return <span className={`fase ${cls}`}><i />{txt}</span>
}

/** Carga asíncrona con estado de error, sin librerías. */
export function useCarga<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [datos, setDatos] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [v, setV] = useState(0)
  useEffect(() => {
    let vivo = true
    setCargando(true); setError(null)
    fn().then(d => { if (vivo) setDatos(d) }).catch(e => { if (vivo) setError(e.message) }).finally(() => { if (vivo) setCargando(false) })
    return () => { vivo = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, v])
  return { datos, error, cargando, recargar: () => setV(x => x + 1) }
}
