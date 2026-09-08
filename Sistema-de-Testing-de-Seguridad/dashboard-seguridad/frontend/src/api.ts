// Cliente HTTP mínimo. Misma origen en producción; proxy de Vite en desarrollo.

export class ApiError extends Error {
  estado: number
  cuerpo: Record<string, unknown> | null
  constructor(mensaje: string, estado: number, cuerpo: Record<string, unknown> | null) {
    super(mensaje)
    this.estado = estado
    this.cuerpo = cuerpo
  }
}

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const r = await fetch(ruta, { cache: 'no-store', ...init })
  let cuerpo: Record<string, unknown> | null = null
  try {
    cuerpo = await r.json()
  } catch {
    cuerpo = null
  }
  if (!r.ok) throw new ApiError((cuerpo?.error as string) || r.statusText, r.status, cuerpo)
  return cuerpo as T
}

export const api = {
  get: <T>(ruta: string) => pedir<T>(ruta),
  post: <T>(ruta: string, datos?: unknown) =>
    pedir<T>(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos ?? {}) }),
  put: <T>(ruta: string, datos?: unknown) =>
    pedir<T>(ruta, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos ?? {}) }),
  delete: <T>(ruta: string) => pedir<T>(ruta, { method: 'DELETE' }),
}

// ── Objetivos (compartidos) ──
export interface ObjetivoRegistrado {
  nombre: string; tipo: string; descripcion: string; proposito: string; con_coste: boolean
  sirve_para_deepteam: boolean; destino: string; permite_solo_llm?: boolean; config: Record<string, unknown>
}
export interface ResultadoPrueba {
  ok: boolean; fase: string; tipo?: string; bloqueado?: boolean; capa?: string; motivo?: string
  texto?: string; error?: string | null; latencia_ms: number
}

// ── Red Turing ──
export interface CorridaResumen {
  archivo: string
  es_baseline: boolean
  objetivo: string
  tipo_objetivo: string
  inicio: string
  duracion_s: number
  juez_activo: boolean
  total: number
  evaluados: number
  exitosos: number
  errores: number
  asr: number
  falsos_positivos: number | null
}

export interface Veredicto {
  exito: boolean
  confianza: 'baja' | 'media' | 'alta'
  detector: string
  evidencia: string
}

export interface Resultado {
  caso: {
    id: string
    categoria: string
    tecnica: string
    payload: string
    objetivo: string
    severidad: string
    benigno: boolean
    notas: string
    archivo_origen: string
  }
  respuesta: {
    texto: string
    bloqueado: boolean
    motivo: string
    capa: string
    latencia_ms: number
    error: string | null
    crudo: { guardrail?: { es_seguro: boolean; motivo: string; capa: string; latencia_ms: number }; llm_pese_al_bloqueo?: boolean }
  }
  veredicto: Veredicto
  veredicto_llm: Veredicto | null
}

export interface Informe {
  objetivo: string
  tipo_objetivo: string
  inicio: string
  duracion_s: number
  juez_activo: boolean
  resumen: {
    total: number
    evaluados: number
    exitosos: number
    errores: number
    asr: number
    latencia_mediana_ms: number
    evaluados_llm?: number
    cedidos_llm?: number
    asr_llm?: number | null
  }
  asr_por_categoria: Record<string, { total: number; exitosos: number; asr: number; ids: string[] }>
  asr_llm_por_categoria?: Record<string, { total: number; exitosos: number; asr: number; ids: string[] }>
  asr_por_capa_que_bloqueo: Record<string, { total: number; exitosos: number; asr: number }>
  resultados: Resultado[]
}

export interface Objetivo { nombre: string; tipo: string; destino: string; con_coste: boolean }
export interface Plan {
  objetivo: string; tipo: string; con_coste: boolean; total: number; benignos: number
  por_categoria: Record<string, number>; por_severidad: Record<string, number>; por_suite: Record<string, number>
  workers: number; usar_juez: boolean
}
export interface EstadoCorrida {
  id: string; fase: string; activa: boolean; objetivo: string; tipo: string; inicio: string; total: number
  completados: number; penetraron: number; contenidos: number; errores: number; asr_parcial: number
  cancelacion_pedida: boolean; archivo: string | null; archivo_html: string | null; mensaje: string
  peticion: Record<string, unknown>; eventos: number
}

// ── DeepTeam ──
export interface Vulnerabilidad { nombre: string; descripcion: string; tipos: string[]; recomendada: boolean; contenido_daniino: boolean }
export interface Ataque { nombre: string; descripcion: string; para_que: string; multi_turno: boolean; usa_llm: boolean; parametros: string[]; recomendado: boolean }
export interface ModeloPreset { id: string; nombre: string; nota: string }
export interface ConfigDT {
  equipo?: string; objetivo_por_defecto?: string
  modelo_adversario: string; modelo_juez: string; en_espanol: boolean; ataques_por_tipo: number; max_concurrentes: number; proposito: string
}
export interface Catalogo { vulnerabilidades: Vulnerabilidad[]; ataques: Ataque[]; modelos: ModeloPreset[]; objetivos: ObjetivoRegistrado[]; config: ConfigDT }

export interface EvaluacionResumen {
  archivo: string; etiqueta: string; objetivo?: string; inicio: string; modo: string; modelo_adversario: string; modelo_juez: string
  total: number; evaluados: number; fallidos: number; errores: number; tasa_fallo: number; cvss: number | null; duracion_s: number
}
export interface CasoDT {
  vulnerabilidad: string; tipo: string | null; ataque: string; payload: string | null; respuesta_tramibot: string | null
  score: number | null; razon_juez: string | null; error: string | null; coste_simulacion?: number | null; coste_evaluacion?: number | null
  turnos: { rol: string; contenido: string }[]
}
export interface Evaluacion {
  archivo: string; etiqueta?: string; objetivo?: string; tipo_objetivo?: string; inicio: string; duracion_s: number; modo: string; con_guardrail?: boolean
  modelo_adversario?: string; modelo_juez?: string; en_espanol?: boolean; llamadas_al_agente?: number; cvss?: number | null
  por_vulnerabilidad?: { vulnerabilidad: string; tipo: string; tasa_mitigacion: number; aprobados: number; fallidos: number; errores: number }[]
  por_ataque?: { ataque: string; tasa_mitigacion: number; aprobados: number; fallidos: number; errores: number }[]
  resultado?: ResumenDT
  casos: CasoDT[]
}
export interface ResumenDT {
  total: number; aguantaron: number; cedieron: number; errores: number
  errores_detalle: { vulnerabilidad: string; tipo: string | null; ataque: string | null; error: string; culpable: 'adversario' | 'juez' | 'agente' }[]
  cedieron_detalle: { vulnerabilidad: string; tipo: string | null; ataque: string | null; razon: string }[]
}
export interface EstadoDT {
  id: string; fase: string; activa: boolean; inicio: string; total_estimado: number; llamadas_al_agente: number
  archivo: string | null; mensaje: string; duracion_s: number; peticion: Record<string, unknown>; resultado?: ResumenDT | null
}
