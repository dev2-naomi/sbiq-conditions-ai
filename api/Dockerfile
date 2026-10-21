# Lambda container for the SBIQ Conditions Evaluator API.
# Build context is the repo root.
FROM public.ecr.aws/docker/library/python:3.11-slim

# Lambda Web Adapter (includes Runtime Interface Client for non-AWS base images).
# response_stream invoke mode is required for real token-by-token SSE streaming.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /var/task

ENV PORT=8080
ENV AWS_LWA_INVOKE_MODE=response_stream
ENV AWS_LWA_READINESS_CHECK_PATH=/health

# Per-stage tag so dev and prod do not push the same immutable ECR asset.
ARG STAGE=local
LABEL sbiq.stage=$STAGE

COPY requirements.txt ./
COPY api/requirements.txt ./api-requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -r api-requirements.txt

COPY agent.py step_loader.py registry.py ./
COPY tools/ ./tools/
COPY plans/ ./plans/
COPY data/ ./data/
COPY config/ ./config/
COPY api/ ./api/

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
