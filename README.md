# Agente DVR ApuestaTotal (Python)

Este proyecto es un agente de escritorio desarrollado en Python encargado de sincronizar en tiempo real el estado y los eventos de los DVRs Hikvision locales con la API centralizada de ApuestaTotal. 

El agente extrae la información a través del protocolo **ISAPI** de Hikvision y la envía de forma segura a los endpoints correspondientes de ApuestaTotal.

---

## 🚀 Arquitectura y Funcionamiento

El sistema se compone de varios módulos clave que se ejecutan de manera concurrente gracias al uso de hilos (`threading`):

### 1. Interfaz Gráfica y System Tray (`tkinter` + `pystray`)
El agente cuenta con una interfaz gráfica nativa construida con `tkinter`. 
- **Configuración Inicial:** Provee un formulario donde el usuario ingresa sus credenciales de la API de ApuestaTotal, y las credenciales del DVR (Usuario, Contraseña, CECO, IP).
- **Auto-descubrimiento:** Si el usuario no ingresa la IP del DVR, el script (`conecction_dvr.py`) utiliza el protocolo SADP (Multicast UDP) para escanear la red local y auto-completar la IP del DVR más cercano.
- **Logs en tiempo real:** Todo lo que sucede por detrás (las impresiones de `stdout`) se captura mediante una clase `RedirectText` y se inyecta en una consola visual dentro de la aplicación.
- **Minimizado (Bandeja del sistema):** Al cerrar la ventana, el agente no se detiene. En su lugar, usa la librería `pystray` para ocultarse en la barra de tareas de Windows (cerca al reloj), manteniéndose activo en segundo plano sin interrumpir al usuario.

### 2. Sincronización Periódica (Storage & Recording)
El hilo principal (`dvr_worker`) entra en un bucle infinito donde, cada *X minutos* (definidos en la configuración):
1. **Estado de Almacenamiento (Storage):** 
   - Consulta el endpoint ISAPI `/ISAPI/ContentMgmt/Storage/hdd`.
   - Mapea la capacidad total, espacio libre y calcula el porcentaje de uso de cada disco duro instalado.
2. **Estado de Grabación (Recording Status):**
   - **Cámaras en línea:** Revisa `/ISAPI/System/Video/inputs/channels` verificando si el canal está habilitado y si no reporta "NO VIDEO".
   - **Configuración de grabación:** Extrae los `tracks` (`/ISAPI/ContentMgmt/record/tracks`) para validar qué cámaras lógicas tienen configurado el guardado de video en local.
   - **Grabación activa:** Utiliza el endpoint de búsqueda `CMSearchDescription` para validar si existen fragmentos de video guardados en los últimos 5 minutos, confirmando así que la cámara está efectivamente grabando.
3. Envía un reporte compilado en formato JSON a los endpoints `/pf-cctv/v1/dvr/storage-status` y `/pf-cctv/v1/dvr/recording-status`.

### 3. Stream de Eventos en Tiempo Real (AlertStream)
En paralelo a la sincronización periódica, un hilo demonio (`daemon thread`) mantiene una conexión HTTP abierta de larga duración (`stream=True`) con `/ISAPI/Event/notification/alertStream`.
- Cuando el DVR detecta un evento (pérdida de video, disco duro lleno, etc.), envía un trozo de XML por este stream.
- El agente lee el flujo, extrae la etiqueta `<eventType>` y `<channelID>` ignorando eventos inactivos.
- Inmediatamente reenvía la alerta al endpoint `/pf-cctv/v1/events-hv`.

---

## 🛠️ Tecnologías y Dependencias

- **Python 3.x**
- **requests:** Para las peticiones HTTP (incluye soporte robusto para `HTTPDigestAuth` requerido por Hikvision).
- **xml.etree.ElementTree:** Para el parseo ligero de respuestas XML.
- **tkinter:** Para la interfaz gráfica principal.
- **pystray & Pillow:** Para la funcionalidad de minimizado en la bandeja del sistema.
- **PyInstaller:** Para compilar todo el proyecto en un único archivo `.exe` distribuible.

---

## ⚙️ Cómo Compilar el Ejecutable

Para empaquetar este script en un archivo `.exe` que pueda correr en cualquier Windows sin tener Python instalado:

1. Instala las dependencias:
   ```cmd
   pip install -r requirements.txt
   ```
2. Ejecuta PyInstaller con las banderas correctas:
   ```cmd
   py -m PyInstaller --onefile --noconsole --name "AgenteDVR_AT" dvr_agent.py
   ```
   *Nota: `--noconsole` es crucial para que no se abra la ventana negra del símbolo del sistema por detrás de la interfaz gráfica.*

El archivo ejecutable resultante quedará dentro de la carpeta `/dist/`.

---

## ⚠️ Consideraciones de Red (VPNs)
Dado que el agente necesita comunicarse con `192.168.x.x` (DVR local) y una API externa (`https://pf.api.apuestatotal.pe`), el uso estricto de VPNs corporativas (Split Tunneling deshabilitado) puede bloquear el acceso al DVR.
Si hay errores de "Connection Timeout" al contactar al DVR, asegúrate de que el cliente VPN permita acceso LAN (*Local LAN access*), o configura una ruta estática en Windows que apunte hacia el gateway local para la IP del DVR.

para agregar la ruta estatica en openvpn:

abrir openVPN 
buscar el archivo .ovpn (con everyting)
agregar al final esta linea:
route 192.168.1.x 255.255.255.255 net_gateway 
donde agregaras a ip del DVR
puedes validar si se agrego con `route print`
