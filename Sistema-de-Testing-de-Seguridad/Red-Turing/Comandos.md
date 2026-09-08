# 1. Instalar las dependencias de tu agente en el entorno de Red Turing (única vez)

cd Red-Turing
source .venv/bin/activate
pip install -r ../../LangChain-AgenteIA-MultiTool-Seguridad/requirements.txt


python -m redturing correr --objetivo agente-databot --suite prompt_injection --limite 3 --workers 1

python -m redturing correr --objetivo agente-databot --workers 2


# 2. Dashboard: ver las corridas y lanzar nuevas desde el navegador

python -m redturing dashboard
# → http://127.0.0.1:8731  ·  «Nueva corrida» abre el formulario
#   Los objetivos agente/http piden confirmación con el número de llamadas.
#   Ctrl+C detiene el servidor (y cancela la corrida en curso si la hay).
