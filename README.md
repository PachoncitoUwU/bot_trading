# 🤖 Autonomous AI Trading Bot (IQ Option & Binance)

Sistema de trading algorítmico autónomo de alto rendimiento con análisis de confluencias por Inteligencia Artificial, control 100% remoto desde Telegram, meta diaria de ganancias (Take-Profit de 3% a 5% con auto-apagado protector), y freno de seguridad de capital (Stop-Loss de sesión).

---

## 🚀 Características Principales

* **Control Remoto desde Telegram:**
  * `▶️ Iniciar Trading`: Activa el escaneo y fija el capital base de la sesión.
  * `⏹️ Parar Trading`: Detiene inmediatamente nuevas entradas.
  * `🎯 Meta (3% a 5%)`: Barra visual de progreso hacia el objetivo diario.
  * `📊 Saldo y Balance`: Consulta el equity actual y libre en tiempo real.
  * `💰 Ganancias / PnL`: Estadísticas de operaciones ganadas, perdidas y win rate.
  * `⚙️ Fijar Meta`: Alterna objetivos rápidos (+3%, +4%, +5%).
* **Meta de Sesión Inteligente (3% a 5%):**
  * Al alcanzar la meta programada (+3% a +5% del saldo), el bot **se auto-apaga automáticamente** para proteger los beneficios y no devolver dinero al mercado.
* **Stop Loss de Sesión (Protección de Capital):**
  * Freno estricto si se acumula un -3% de pérdida en la sesión para evitar rachas adversas.
* **Staking Proporcional y Seguro:**
  * Posturas escalonadas y controladas para garantizar crecimiento sostenido.
* **Reportes Visuales en Vivo:**
  * Envío automático a Telegram de la tarjeta gráfica con velas reales japonesas de cada entrada y su resultado de cierre (Win/Loss).
* **Modo de Operación 24/7:**
  * Prevención nativa de suspensión de energía en Windows y preparado para VPS en la nube (Docker / Linux).

---

## 🛠️ Requisitos Previos

* **Python 3.11+**
* Cuenta en broker compatible (IQ Option / Binance)
* Token de Bot de Telegram (obtenido vía [@BotFather](https://t.me/BotFather)) y tu ID de chat.

---

## ⚡ Instalación Rápida

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/PachoncitoUwU/bot_trading.git
   cd bot_trading
   ```

2. **Crear entorno virtual e instalar dependencias:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: .\venv\Scripts\activate
   pip install -r backend/requirements.txt
   ```

3. **Configurar variables de entorno (`.env`):**
   Copia `.env.example` a `.env` y añade tus credenciales:
   ```env
   BOT_MODE=TESTNET
   EXCHANGE_ID=iqoption
   IQOPTION_EMAIL=tu_correo@ejemplo.com
   IQOPTION_PASSWORD=tu_contraseña
   IQOPTION_BALANCE_MODE=PRACTICE
   IQOPTION_MARTINGALE_STEPS=[1.0, 2.0, 4.0]

   TELEGRAM_BOT_TOKEN=tu_token_aqui
   TELEGRAM_ADMIN_CHAT_ID=tu_chat_id_aqui
   ```

4. **Iniciar el Bot:**
   * En Windows:
     ```bash
     start.bat
     ```
   * En Linux/Mac:
     ```bash
     uvicorn backend.main:app --host 0.0.0.0 --port 8000
     ```

---

## 🌐 Despliegue 24/7 Gratuito

### Opción 1: Oracle Cloud "Always Free" (Recomendada)
1. Regístrate en [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) para obtener un servidor VPS gratuito de por vida (4 vCPU ARM, 24 GB RAM).
2. Crea una instancia Ubuntu Always Free.
3. Clona el repositorio y lanza el bot con Docker:
   ```bash
   docker-compose up -d --build
   ```

### Opción 2: Ejecución Local 24/7 (Laptop / PC en casa)
El bot incluye `app/core/power_manager.py` (`enable_24_7_execution_mode()`), el cual le indica a Windows no suspenderse ni apagar la red aunque cierres la tapa de la laptop mientras esté conectada al cargador.

---

## 🛡️ Descargo de Responsabilidad (Disclaimer)
El trading algorítmico y de derivados conlleva riesgos financieros. Este software está diseñado para propósitos educativos y de prueba en entornos DEMO / PRACTICE. El usuario asume toda la responsabilidad por las decisiones financieras tomadas.
