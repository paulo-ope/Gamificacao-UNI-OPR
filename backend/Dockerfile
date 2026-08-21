FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Sem build-essential/libpq-dev de propósito (pedido do usuário em 2026-08-21, imagem mais leve
# pra VM): todas as deps de requirements.txt, incluindo psycopg[binary] e as libs com extensão C
# de uvicorn[standard] (uvloop, httptools) e cryptography, já instalam de wheel pré-compilada
# nesta combinação de imagem/arquitetura (confirmado num build real - nenhum "Building wheel for"
# apareceu no log). Se uma dependência futura exigir compilar do zero, o build vai falhar aqui de
# forma clara (ModuleNotFoundError não, e sim erro do pip) - reinstale as duas nesse caso.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

EXPOSE 8000

# Sem --reload: em produção (VM), o reload observa o filesystem e QUALQUER toque nos arquivos
# (ex.: sync do OneDrive na máquina de dev, quando os volumes dev estão montados) reinicia a API
# no meio de requisições/tarefas - incidente real. Para desenvolvimento com hot-reload, use
# docker-compose.dev.yml (re-adiciona os volumes e o --reload).
#
# O entrypoint roda "alembic upgrade head" antes de subir a API, para que migrations novas
# (ex.: as do módulo de Operação Analítica) sejam aplicadas automaticamente a cada deploy,
# sem depender de alguém lembrar de rodar o comando manualmente na VM.
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
