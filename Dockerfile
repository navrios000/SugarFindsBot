FROM python:3.12-slim

WORKDIR /app

# Dependencias necesarias para Playwright/Chromium
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite0 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicación
COPY bot.py config.py ./
COPY handlers/ ./handlers/
COPY utils/ ./utils/
COPY product_processor/ ./product_processor/
COPY inspect_sugargoo.py ./
COPY inspect_weidian.py ./

# Crear usuario no-root
RUN useradd --create-home --shell /bin/bash appuser

# Dar permisos sobre la aplicación
RUN chown -R appuser:appuser /app /home/appuser

# Ejecutar todo lo relacionado con Playwright como appuser
USER appuser

# Instalar Chromium para appuser
RUN playwright install chromium

# Ejecutar bot
CMD ["python", "bot.py"]
