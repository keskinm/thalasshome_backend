cd ../..&&\
source env.sh&&\
gunicorn -b 0.0.0.0:1337 websocket.ws:app --worker-class sanic.worker.GunicornWorker --daemon