FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential libpq-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

EXPOSE 8000

# Sem --reload: em produção (VM), o reload observa o filesystem e QUALQUER toque nos arquivos
# (ex.: sync do OneDrive na máquina de dev, quando os volumes dev estão montados) reinicia a API
# no meio de requisições/tarefas - incidente real. Para desenvolvimento com hot-reload, use
# docker-compose.dev.yml (re-adiciona os volumes e o --reload).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
