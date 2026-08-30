FROM python:3.12-bookworm

WORKDIR /app

# Dependencias Python
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium y todas sus dependencias
RUN python -m playwright install --with-deps chromium

# Copiar proyecto
COPY bot.py config.py ./
COPY handlers/ ./handlers/
COPY utils/ ./utils/
COPY product_processor/ ./product_processor/
COPY inspect_sugargoo.py ./
COPY inspect_weidian.py ./

# Crear usuario para ejecutar el bot
RUN useradd --create-home --shell /bin/bash appuser

# Copiar los navegadores de Playwright al usuario que ejecutará el bot
RUN mkdir -p /home/appuser/.cache && \
    cp -r /root/.cache/ms-playwright /home/appuser/.cache/ && \
    chown -R appuser:appuser /app /home/appuser

USER appuser

# Ruta donde Playwright buscará Chromium
ENV PLAYWRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright

CMD ["python", "bot.py"]
