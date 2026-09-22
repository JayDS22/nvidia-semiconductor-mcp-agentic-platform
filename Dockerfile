# Multi-stage kept simple — Streamlit + Python 3.11 + our deps.
FROM python:3.11-slim

WORKDIR /app

# Install system deps for numpy/pandas wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Seed mock data at build time so first request is fast
RUN python mcp_server/data/seed_wafers.py

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
