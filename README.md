# Sugar Finds Bot

Bot de Telegram para el grupo Sugar Finds.

**Estado: Fase 2** — genera FINDs automáticamente para productos de
**Weidian**. Taobao y 1688 se detectan pero se publican manualmente
por ahora (ver "Estado actual" más abajo).

## Variables de entorno

| Variable | Descripción |
|---|---|
| `BOT_TOKEN` | Token del bot, obtenido de @BotFather. |
| `ADMIN_IDS` | IDs numéricos de Telegram de los administradores autorizados, separados por comas. |
| `SPREADSHEET_URL` | URL fija que se usa como el link "Spreadsheet" en todos los FINDs. |
| `SUGARGOO_MEMBER_ID` | Tu memberId de SugarGoo, para construir el enlace de afiliado. |
| `SUGARGOO_COUPON` | Código de cupón de SugarGoo (fijo, se muestra en todos los FINDs). |
| `USFANS_REF` | Tu referencia de afiliado de USFans (p.ej. `M3XSLC`), usada para construir enlaces de producto. **No es el cupón.** |
| `USFANS_COUPON` | Código de cupón de USFans (fijo, se muestra en todos los FINDs). **No es la referencia de afiliado.** |

Copia `.env.example` a `.env` y rellena los valores para desarrollo local.
**No subas `.env` a GitHub** (ya está excluido en `.gitignore`).

## Ejecutar en local

```bash
pip install -r requirements.txt
export BOT_TOKEN=xxxxx
export ADMIN_IDS=123456789
export SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/XXX
export SUGARGOO_MEMBER_ID=1130639351717008620
export SUGARGOO_COUPON=XXXXX
export USFANS_REF=M3XSLC
export USFANS_COUPON=XXXXX
python bot.py
```

## Despliegue en Render

El bot expone un health-check HTTP en `$PORT` además de hacer polling
de Telegram, por lo que está desplegado como **Web Service** (no
Background Worker — el `Dockerfile` sirve igual para ambos, pero el
tipo de servicio se elige al crearlo en Render).

1. Crear un servicio en Render apuntando a este repositorio (Render
   detecta el `Dockerfile` automáticamente).
2. En "Environment", añadir todas las variables de la tabla de arriba.
3. Desplegar.

## Requisito externo: Group Privacy

El bot necesita **Group Privacy = OFF** en @BotFather para poder leer
mensajes normales del grupo (no solo comandos). Esto se configura fuera
del código, en la configuración del bot en Telegram.

## Cómo funciona el flujo de un FIND

1. Un administrador manda un link de producto (Weidian/Taobao/1688) al bot.
2. `utils/link_parser.py` detecta la plataforma.
3. Si es **Weidian**: `product_processor/weidian.py` pide la página
   pública del producto (sin sesión, sin navegador) y extrae nombre,
   precio e imágenes.
4. Se añaden `spreadsheet_url` (fijo), el link de SugarGoo con tu
   `memberId` (`utils/affiliate.py`) y los cupones fijos.
5. `utils/find_formatter.py` genera el texto del FIND y el bot lo
   publica en el canal con las fotos.
6. Si es **Taobao/1688**, el bot avisa al admin de que ese FIND hay
   que montarlo a mano por ahora.

## Estado actual (Fase 2)

- ✅ Configuración validada, incluyendo spreadsheet/cupones/memberId.
- ✅ Whitelist de administradores.
- ✅ Detección de enlaces de Weidian/Taobao/1688.
- ✅ Weidian: scraping automático (nombre, precio, fotos) sin sesión ni navegador.
- ✅ Generación de enlace de afiliado SugarGoo con memberId.
- ✅ Formato del FIND con "Spreadsheet" como link clicable.
- ⏳ Taobao/1688: solo detección, sin scraping automático (protección
  anti-bot de Alibaba; decisión pendiente sobre API de pago vs Playwright).
- ⏳ USFans: sin enlace de afiliado propio todavía (solo cupón fijo).
- ⚠️ **Calibración pendiente en Weidian**: si el nombre/precio/fotos
  salen mal en un FIND real, ejecuta `python inspect_weidian.py "<link>"`
  y comparte el `weidian_page.html` resultante para ajustar el parser
  en `product_processor/weidian.py`.
