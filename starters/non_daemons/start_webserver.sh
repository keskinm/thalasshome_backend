cd ../..&&\
source env.sh&&\
gunicorn -b 0.0.0.0:8000 dashboard.main:app