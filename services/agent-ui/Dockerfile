FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir streamlit requests

COPY app.py .

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]