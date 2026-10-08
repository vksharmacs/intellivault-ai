FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd -r app && useradd -r -g app app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . .
RUN mkdir -p /data/uploads && chown app:app /data/uploads
USER app
EXPOSE 8000
CMD ["sh","-c","uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
