# Build the existing React frontend without changing its source.
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Python/Flask production image.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEV_MODE=false \
    SEED_DEFAULT_SETTINGS=true
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
# Flask serves the built React app from backend/static.
COPY --from=frontend-build /app/frontend/dist/ /app/backend/static/
COPY deploy-entrypoint.sh /app/deploy-entrypoint.sh
RUN chmod +x /app/deploy-entrypoint.sh
WORKDIR /app/backend
EXPOSE 10000
CMD ["/app/deploy-entrypoint.sh"]
