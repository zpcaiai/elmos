FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
EXPOSE 8090
CMD ["uvicorn", "migration_agent.app:app", "--host", "0.0.0.0", "--port", "8090"]
