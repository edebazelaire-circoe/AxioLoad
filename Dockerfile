FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLO_DATA_DIR=/app/data PLO_DEMO_MODE=0
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[solver,routing]"
RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["pallet-optimizer", "--data-dir", "/app/data", "serve", "--host", "0.0.0.0", "--port", "8000"]
