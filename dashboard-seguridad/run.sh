#!/usr/bin/env bash
# Arranca el dashboard de seguridad (Red Turing + DeepTeam).
#   ./run.sh            → compila el frontend si hace falta y sirve todo en http://127.0.0.1:8740
#   ./run.sh dev        → backend en 8740 + Vite con recarga en caliente en http://127.0.0.1:5173
#   ./run.sh build      → solo compila el frontend
#
# Intérprete: usa $PYTHON si está definido; si no, el `python` activo. Debe ser
# el entorno donde instalaste backend/requirements.txt (y, si atacas un agente
# Python importable, también las dependencias de ese agente).
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python}"

case "${1:-}" in
  build) (cd frontend && npm install --silent && npm run build) ;;
  dev)
    (cd backend && "$PY" -m uvicorn app:app --host 127.0.0.1 --port 8740 --reload) &
    (cd frontend && npm install --silent && npm run dev)
    ;;
  *)
    if [ ! -d frontend/dist ]; then (cd frontend && npm install --silent && npm run build); fi
    echo "  Dashboard en http://127.0.0.1:8740  (Ctrl+C para detener)"
    cd backend && exec "$PY" -m uvicorn app:app --host 127.0.0.1 --port 8740
    ;;
esac
