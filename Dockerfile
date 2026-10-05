FROM python:3.11-slim

WORKDIR /app
COPY . .
# [dev] is needed: the API validates its responses with jsonschema.
RUN pip install --no-cache-dir -e ".[dev]"

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn backend.api.app:create_app --factory --host 0.0.0.0 --port ${PORT}"]
