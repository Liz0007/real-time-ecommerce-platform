FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir .

# Bake the embedding model into the image, so a new container never downloads
# it: no startup delay, no internet access to huggingface.co needed at runtime.
# Must match EMBEDDING_MODEL_NAME in app/rag.py. If the two drift apart, the
# offline setting below makes the service fail at the first embed instead of
# quietly downloading a different model.
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; \
m = SentenceTransformer('${EMBEDDING_MODEL}'); \
print('baked', '${EMBEDDING_MODEL}', m.get_sentence_embedding_dimension(), 'dims')"

# From here on, use only what is in the image.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY app/ ./app/
COPY evals/ ./evals/
COPY docs/ ./docs/

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
