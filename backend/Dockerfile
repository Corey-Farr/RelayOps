FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY relayops ./relayops
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home relayops
USER relayops
EXPOSE 8000 9000
CMD ["uvicorn", "relayops.main:app", "--host", "0.0.0.0", "--port", "8000"]
