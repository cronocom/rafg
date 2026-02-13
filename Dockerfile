# ═══════════════════════════════════════════════════════════
# RAGF API Container
# Multi-stage build para optimizar tamaño
# ═══════════════════════════════════════════════════════════

FROM python:3.11-slim as builder

WORKDIR /build

# Instalar dependencias de compilación
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de dependencias
COPY requirements.txt .

# Instalar dependencias en directorio local
RUN pip install --user --no-cache-dir -r requirements.txt

# ═══════════════════════════════════════════════════════════
# Imagen final (slim)
# ═══════════════════════════════════════════════════════════

FROM python:3.11-slim

WORKDIR /app

# Instalar curl para healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copiar dependencias instaladas desde builder
COPY --from=builder /root/.local /root/.local

# Asegurar que scripts están en PATH
ENV PATH=/root/.local/bin:$PATH

# Copiar código fuente
COPY shared/ /app/shared/
COPY gateway/ /app/gateway/
COPY audit/ /app/audit/
COPY tests/ /app/tests/

# Crear directorio para logs
RUN mkdir -p /app/logs

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Exponer puerto
EXPOSE 8000

# Comando de inicio con Uvicorn (ASGI server)
# NO cambiar de usuario para evitar problemas de permisos
CMD ["uvicorn", "gateway.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
