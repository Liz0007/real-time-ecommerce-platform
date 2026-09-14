FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY generate_orders.py requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --rate/--duration/--url are passed via docker-compose's `command:` override
# so they're easy to tweak without rebuilding the image.
ENTRYPOINT ["python", "generate_orders.py"]