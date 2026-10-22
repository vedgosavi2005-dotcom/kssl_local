# Parallax Analyst for KSSL_Deploy v2: the product's built frontend + the chat widget + the agent
# service, as one image. Build context: the REPO ROOT (see docker-compose.yml).

# 1. the product's own frontend, built as deploy/Dockerfile.web builds it (npm ci + vite build)
FROM node:20-alpine AS product
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src/ ./src/
RUN npx vite build

# 2. the chat widget (it bundles adapter/product.json)
FROM node:22-slim AS widget
WORKDIR /w
COPY parallax-agent/widget/package.json parallax-agent/widget/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY parallax-agent/widget/ ./
COPY parallax-agent/adapter/ /adapter/
RUN npx vite build --outDir /out --emptyOutDir

# 3. the agent service and gateway
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY parallax-agent/service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY parallax-agent/service/ ./
COPY parallax-agent/adapter/ /adapter/
COPY --from=widget /out ./static
COPY --from=product /app/dist /product-dist
ENV ADAPTER_DIR=/adapter PRODUCT_DIST=/product-dist
EXPOSE 8098
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8098", "--proxy-headers"]
