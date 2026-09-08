import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api, type ConfigDT, type EstadoCorrida, type EstadoDT } from './api'
import Objetivos from './pages/Objetivos'
import Guia from './pages/Guia'
import RedTuringLista from './pages/RedTuringLista'
import RedTuringDetalle from './pages/RedTuringDetalle'
import RedTuringNueva from './pages/RedTuringNueva'
import RedTuringLive from './pages/RedTuringLive'
import DeepTeamLista from './pages/DeepTeamLista'
import DeepTeamDetalle from './pages/DeepTeamDetalle'
import DeepTeamNueva from './pages/DeepTeamNueva'
import DeepTeamEstado from './pages/DeepTeamEstado'

export default function App() {
  // La barra lateral muestra si hay algo corriendo en cualquiera de los dos motores.
  const [rt, setRt] = useState<EstadoCorrida | null>(null)
  const [dt, setDt] = useState<EstadoDT | null>(null)
  const [equipo, setEquipo] = useState('LLM Red Teaming Framework')
  useEffect(() => { api.get<ConfigDT>('/api/deepteam/config').then(c => c.equipo && setEquipo(c.equipo)).catch(() => undefined) }, [])
  useEffect(() => {
    let vivo = true
    const tick = async () => {
      try {
        const [a, b] = await Promise.all([api.get<EstadoCorrida | null>('/api/redturing/corrida-activa'), api.get<EstadoDT | null>('/api/deepteam/estado')])
        if (vivo) { setRt(a); setDt(b) }
      } catch { /* backend apagado: la UI lo dirá en cada página */ }
    }
    tick()
    const t = setInterval(tick, 3000)
    return () => { vivo = false; clearInterval(t) }
  }, [])

  return (
    <div className="app">
      <aside className="lateral">
        <div className="marca">
          <div className="logo">SL</div>
          <div>
            <h1>Seguridad LLM</h1>
            <p>{equipo}</p>
          </div>
        </div>

        <nav>
          <h2>Inicio</h2>
          <NavLink to="/guia">Guía de uso</NavLink>
          <NavLink to="/objetivos">Objetivos (agentes a probar)</NavLink>

          <h2>Red Turing</h2>
          <p className="nav-desc">Corpus fijo, veredictos determinísticos. Regresión.</p>
          <NavLink to="/redturing" end>Corridas</NavLink>
          <NavLink to="/redturing/nueva">Nueva corrida</NavLink>
          {rt?.activa && <NavLink to="/redturing/live" className="viva"><i /> En curso · {rt.completados}/{rt.total}</NavLink>}

          <h2>DeepTeam</h2>
          <p className="nav-desc">Ataques generados por un LLM adversario, juzgados por otro. Exploración.</p>
          <NavLink to="/deepteam" end>Evaluaciones</NavLink>
          <NavLink to="/deepteam/nueva">Nueva evaluación</NavLink>
          {dt?.activa && <NavLink to="/deepteam/estado" className="viva"><i /> En curso · {dt.llamadas_al_agente}/{dt.total_estimado}</NavLink>}
        </nav>

        <footer className="lateral-pie">
          Solo localhost. Los informes contienen los payloads que atravesaron tus defensas.
        </footer>
      </aside>

      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/guia" replace />} />
          <Route path="/guia" element={<Guia />} />
          <Route path="/objetivos" element={<Objetivos />} />
          <Route path="/redturing" element={<RedTuringLista />} />
          <Route path="/redturing/corrida/:archivo" element={<RedTuringDetalle />} />
          <Route path="/redturing/nueva" element={<RedTuringNueva />} />
          <Route path="/redturing/live" element={<RedTuringLive />} />
          <Route path="/deepteam" element={<DeepTeamLista />} />
          <Route path="/deepteam/evaluacion/:archivo" element={<DeepTeamDetalle />} />
          <Route path="/deepteam/nueva" element={<DeepTeamNueva />} />
          <Route path="/deepteam/estado" element={<DeepTeamEstado />} />
          <Route path="*" element={<Navigate to="/redturing" replace />} />
        </Routes>
      </main>
    </div>
  )
}
