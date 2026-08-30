FROM python:3.12-slim

WORKDIR /app

# Ubicación compartida de los navegadores de Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Dependencias básicas
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium + dependencias del sistema
RUN playwright install --with-deps chromium

# Copiar proyecto
COPY bot.py config.py ./
COPY handlers/ ./handlers/
COPY utils/ ./utils/
COPY product_processor/ ./product_processor/
COPY inspect_sugargoo.py ./
COPY inspect_weidian.py ./

# Crear usuario del bot
RUN useradd --create-home --shell /bin/bash appuser

# Dar permisos al usuario sobre el proyecto y Playwright
RUN chown -R appuser:appuser /app /home/appuser /ms-playwright

USER appuser

CMD ["python", "bot.py"]
