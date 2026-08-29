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
    libxcomposite1 \
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

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium de Playwright
RUN playwright install chromium

# Copiar aplicación
COPY bot.py config.py ./
COPY handlers/ ./handlers/
COPY utils/ ./utils/
COPY inspect_sugargoo.py ./

# Usuario no privilegiado
RUN useradd --create-home --shell /bin/bash appuser

# Dar acceso al navegador descargado
RUN chown -R appuser:appuser /home/appuser

USER appuser

CMD ["python", "bot.py"]
