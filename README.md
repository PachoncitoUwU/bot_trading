# 🤖 Autonomous AI Trading Bot (IQ Option & Telegram Hub)

> ☁️ **ESTADO: DESPLEGADO Y OPERANDO 24/7 EN LA NUBE**  
> Sistema de trading algorítmico autónomo de alta precisión con **Estrategia Única Especializada**, control remoto integral desde Telegram, meta diaria de beneficios con auto-apagado protector (+3.5%), y freno de seguridad de capital (Stop-Loss estricto al -3.0%).

---

## ☁️ Arquitectura en la Nube: 2 Tecnologías de Despliegue

El bot está diseñado y optimizado para ejecutarse en la nube de forma ininterrumpida sin depender de una computadora encendida en casa, utilizando **dos tecnologías complementarias**:

```
                       ┌────────────────────────────────────────────────────────┐
                       │               REPOSITORIO GITHUB (main)                │
                       └──────────────────────────┬─────────────────────────────┘
                                                  │
                    ┌─────────────────────────────┴─────────────────────────────┐
                    ▼                                                           ▼
       [TECNOLOGÍA 1: DOCKER & VPS]                              [TECNOLOGÍA 2: CLOUD PaaS (RENDER)]
   Contenedores Docker aislados en Linux                       Despliegue continuo serverless con CI/CD
   ├── backend (FastAPI + Uvicorn + Python 3.11)               ├── Autodespliegue por Webhook en cada git push
   ├── frontend (Nginx Web Dashboard)                          ├── Detección de runtime.txt (Python 3.11.8)
   └── Volumen persistente SQLite y auto-reinicio              └── requirements.txt optimizado en raíz
                    │                                                           │
                    └─────────────────────────────┬─────────────────────────────┘
                                                  ▼
                          [IQ OPTION API] ◄───► [TELEGRAM VIP BOT 24/7]
```

### 1. Tecnología 1: Docker & Docker Compose (VPS Cloud Linux)
* **Infraestructura:** Servidores VPS en la nube (Hetzner, Oracle Cloud Always Free, DigitalOcean, Contabo).
* **Stack:**
  * `backend`: Contenedor Dockerizado con Python 3.11, FastAPI, WebSocket Hub y motor de ejecución asíncrono.
  * `frontend`: Contenedor Nginx Alpine sirviendo el Dashboard interactivo en tiempo real.
* **Resiliencia:** Política `restart: unless-stopped` que reanuda el bot automáticamente ante reinicios del servidor.
* **Comando de arranque:**
  ```bash
  docker compose up -d --build
  ```

### 2. Tecnología 2: Cloud PaaS Serverless (Render / Railway / Koyeb)
* **Infraestructura:** Plataforma como servicio conectada directamente a la rama `main` de GitHub.
* **Automatización CI/CD:** Cada cambio subido con `git push` reconstruye y actualiza el bot en la nube automáticamente sin intervención manual.
* **Configuración nativa:**
  * [`runtime.txt`](runtime.txt): Fija la versión de Python en `python-3.11.8`.
  * [`requirements.txt`](requirements.txt): Gestión de dependencias limpias para compilación sin errores en entornos Linux en la nube.
  * Resolución de rutas universal en `backend/main.py` para compatibilidad de rutas relativas.

---

## 🎯 Estrategia Única Especializada: Trend Pullback & Rejection Sniper (5m)

Para maximizar la tasa de acierto y eliminar el ruido del mercado, el bot **se especializa en una única estrategia institucional** de alta probabilidad, descartando entradas dispersas o persecución de velas:

```
[1. Tendencia Clara EMA 50/100] ──> [2. Pullback a Zona de Valor (EMA 21/BB)] ──> [3. Vela de Rechazo Pinbar >=60%] ──> [4. Disparo Sniper 5m]
```

### Pilares del Setup Único:
1. **Filtro de Tendencia Absoluto (Cero Contratendencia):**
   * **Solo CALL (Compras):** El precio debe estar por encima de la EMA 50 y EMA 100 con pendiente alcista.
   * **Solo PUT (Ventas):** El precio debe estar por debajo de la EMA 50 y EMA 100 con pendiente bajista.
2. **Zona de Valor (Retroceso / Pullback):**
   * Se espera pacientemente el retroceso hacia la media de Bollinger o la EMA de 21 periodos. Queda **prohibido entrar persiguiendo velas gigantes de impulso**.
3. **Gatillo de Rechazo Institucional (Price Action):**
   * La vela en la zona de soporte/resistencia debe dejar una **mecha de absorción superior al 60% del rango total de la vela** (Martillos, Pinbars, Estrellas Fugaces).
   * Confirmación por inflexión de RSI saliendo de zonas extremas (<=38 para CALL, >=62 para PUT).
4. **Temporalidad y Expiración:**
   * **Expiración a 5 minutos:** Elimina el ruido aleatorio de las velas de 60 segundos, permitiendo que el rebote institucional se complete limpiamente.

---

## ⚙️ Configuración de Variables de Entorno (`.env`)

El archivo `.env` en el servidor cloud gestiona todas las credenciales y reglas de gestión monetaria:

```env
# MODO DE OPERACIÓN
BOT_MODE=TESTNET
EXCHANGE_ID=iqoption
USE_TESTNET=true

# CREDENCIALES IQ OPTION
IQOPTION_EMAIL=tu_correo@ejemplo.com
IQOPTION_PASSWORD=tu_contraseña
IQOPTION_BALANCE_MODE=PRACTICE
IQOPTION_MARTINGALE_STEPS=[50.0, 100.0, 200.0]

# ACTIVOS Y TEMPORALIDAD
TRADING_SYMBOLS=["EURUSD-OTC", "GBPUSD-OTC", "EURGBP-OTC", "EURJPY-OTC", "USDCHF-OTC", "GBPJPY-OTC", "NZDUSD-OTC", "AUDCAD-OTC"]
DEFAULT_TIMEFRAME=1m

# GESTIÓN DE RIESGO ESTRICTA
MAX_DAILY_DRAWDOWN_PCT=3.0
MAX_ACCOUNT_EXPOSURE_PCT=20.0
MAX_RISK_PER_TRADE_PCT=1.0
CIRCUIT_BREAKER_MAX_ERRORS=3

# CONTROL REMOTO TELEGRAM
TELEGRAM_BOT_TOKEN=tu_token_aqui
TELEGRAM_ADMIN_CHAT_ID=tu_chat_id_aqui
TELEGRAM_CHANNEL_ID=
TELEGRAM_SIGNAL_TTL_SECONDS=45
TELEGRAM_HEARTBEAT_MINUTES=60

# ENTORNO Y BASE DE DATOS
APP_ENV=development
PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./trading_bot.db
```

---

## 📱 Control Remoto 100% Móvil desde Telegram

Toda la supervisión y control del bot se realiza desde el celular mediante botones interactivos en Telegram:

* **`▶️ Iniciar Trading`**: Activa el escaneo autónomo en vivo y fija el balance de partida.
* **`⏹️ Parar Trading`**: Pausa inmediatamente nuevas entradas.
* **`🎯 Meta y Progreso`**: Visualiza la barra de avance hacia el Take-Profit diario (+3.5%).
* **`📊 Saldo y Balance`**: Consulta de equity y fondos disponibles en IQ Option.
* **`💰 Ganancias / PnL`**: Reporte de operaciones ganadas, perdidas y win rate.
* **Auto-Apagado Protector**: Al alcanzar la meta fijada (+3.5%), el bot se desconecta solo y asegura los beneficios sin sobreoperar.
* **Freno Stop-Loss**: Si se alcanza el -3.0% de pérdida en el día, se bloquea la sesión para proteger el capital.

---

## 🚀 Actualización y Despliegue de Cambios

Para actualizar el bot en la nube tras cualquier modificación:

```bash
git add .
git commit -m "feat: actualizar bot y estrategia sniper"
git push origin main
```

* **En Render / PaaS:** El despliegue se inicia automáticamente al recibir el `git push`.
* **En VPS Docker:**
  ```bash
  ssh root@TU_IP_VPS
  cd /root/bot
  git pull origin main
  docker compose up -d --build
  ```

---

## 🛡️ Descargo de Responsabilidad (Disclaimer)
El trading algorítmico y de derivados conlleva riesgos financieros. Este software está diseñado para propósitos educativos y de prueba en entornos DEMO / PRACTICE.
