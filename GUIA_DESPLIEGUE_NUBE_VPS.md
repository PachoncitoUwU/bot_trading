# ☁️ GUÍA PASO A PASO: DESPLIEGUE DEL BOT EN LA NUBE (VPS 24/7)

Esta guía te explica cómo poner a funcionar tu Bot de Trading en un servidor en la nube para que esté **activo las 24 horas del día, los 7 días de la semana**, sin que tengas que tener tu computador encendido.

Todo lo controlarás directamente desde tu celular a través de **Telegram**.

---

## 💰 1. ¿Qué servicio contratar y cuánto cuesta?

Para correr este bot necesitas un **VPS (Servidor Privado Virtual)** con Linux (Ubuntu 22.04 o 24.04 LTS).

| Proveedor | Plan Recomendado | Costo Mensual | Ventajas |
| :--- | :--- | :--- | :--- |
| 🥇 **Hetzner Cloud** *(Recomendado)* | Plan **CX22** (2 vCPU, 4GB RAM) | **~€3.79 EUR/mes (~$4 USD)** | El más rápido, ultra-estable y económico de Europa/EE.UU. |
| 🥈 **DigitalOcean** | Basic Droplet (1 vCPU, 1GB o 2GB RAM) | **$6 USD/mes** | Muy fácil de usar, soporte en español y pago con tarjeta o PayPal. |
| 🥉 **Contabo** | Cloud VPS S (4 vCPU, 6GB RAM) | **~$5.50 USD/mes** | Mucha potencia por poco dinero. |

> [!TIP]
> **Recomendación:** Con el plan más básico de **Hetzner** o **DigitalOcean** ($4 a $6 USD/mes) el bot vuela con un consumo de recursos mínimo (menos del 10% de CPU).

---

## 🚀 2. Proceso de Configuración Paso a Paso (Solo se hace una vez)

### Paso 1: Crear el Servidor en la web del proveedor
1. Entra a [Hetzner](https://www.hetzner.com/cloud) o [DigitalOcean](https://www.digitalocean.com) y regístrate.
2. Crea un nuevo servidor:
   * **Sistema Operativo:** Ubuntu 22.04 LTS o 24.04 LTS.
   * **Ubicación:** Frankfurt, Helsinki o Nueva York (cualquiera tiene excelente latencia con IQ Option).
   * **Autenticación:** Elige "Password" (contraseña) para mayor facilidad.
3. Te darán la **Dirección IP** de tu servidor (ejemplo: `168.119.50.23`).

---

### Paso 2: Conectarte a tu servidor
* En tu PC abre la terminal (**PowerShell** o **Símbolo del sistema**) y escribe:
  ```bash
  ssh root@TU_IP_DEL_SERVIDOR
  ```
  *(Introduce la contraseña que creaste o la que te enviaron al correo).*

---

### Paso 3: Instalar Docker en el Servidor
Copia y pega este comando en la pantalla negra del servidor (se instala en 60 segundos):
```bash
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
```

---

### Paso 4: Subir los archivos del bot
Puedes subir los archivos desde tu computadora hacia el VPS con un solo comando desde PowerShell en tu PC:
```powershell
scp -r "c:\Users\beatr\OneDrive\Escritorio\bot" root@TU_IP_DEL_SERVIDOR:/root/bot
```
*(O si tienes el bot en GitHub, en el servidor simplemente haces `git clone TU_REPOSITORIO`).*

---

### Paso 5: Encender el Bot en la Nube
En el servidor entra a la carpeta del bot y arranca los contenedores:
```bash
cd /root/bot
docker compose up -d --build
```

**¡Listo!** El bot ya está corriendo dentro del servidor en la nube. Puedes apagar tu computador, desconectar internet o irte a dormir. El bot seguirá funcionando.

---

## 📱 3. ¿Cómo lo controlas desde tu Celular con Telegram?

El bot se conecta automáticamente al mismo canal y chat de Telegram que ya tienes configurado en tu `.env`.

Desde cualquier lugar del mundo abres Telegram en tu celular y tienes acceso a los botones táctiles:

* **`▶️ Iniciar Bot`**: Pone al bot a buscar operaciones en el mercado.
* **`⏹️ Detener Bot`**: Lo pausa de inmediato si no quieres operar.
* **`🎯 Meta y Progreso`**: Te muestra cuánto dinero lleva ganado hoy y la barra de avance (`[🟩🟩🟩⬜⬜]`).
* **`⏱️ Modo Horas`**: Alterna entre trabajar 1 hora y descansar 1 hora para no sobreoperar.
* **`📊 Estado y Balance`**: Te dice el saldo real actual en IQ Option.

### 🏆 Auto-Apagado de Seguridad:
Cuando el bot alcance el **3.5% de ganancia** (o la meta que fijes), él solo se desconecta de IQ Option, te manda el mensaje de celebración con el saldo total a tu Telegram y se estaciona hasta que tú decidas volver a iniciarlo.

---

## 🛠️ Comandos útiles para revisar el servidor (opcional)

Si algún día quieres ver lo que está haciendo el bot por dentro desde la terminal:
* **Ver registros en vivo:**
  ```bash
  docker logs -f trading_bot_backend
  ```
* **Reiniciar el bot:**
  ```bash
  docker compose restart
  ```
* **Detener todo:**
  ```bash
  docker compose down
  ```
