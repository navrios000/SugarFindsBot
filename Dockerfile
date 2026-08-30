FROM python:3.12-slim

WORKDIR /app

# Dependencias básicas necesarias para Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium y todas sus dependencias del sistema
RUN playwright install --with-deps chromium

# Copiar proyecto
COPY bot.py config.py ./
COPY handlers/ ./handlers/
COPY utils/ ./utils/
COPY product_processor/ ./product_processor/
COPY inspect_sugargoo.py ./
COPY inspect_weidian.py ./

# Crear usuario no-root
RUN useradd --create-home --shell /bin/bash appuser

# Dar permisos al usuario
RUN chown -R appuser:appuser /app /home/appuser

USER appuser

CMD ["python", "bot.py"]
