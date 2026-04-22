import os
os.environ['NO_PROXY'] = '*'
import sys
import time
import datetime
import threading
import json
import ctypes
import xml.etree.ElementTree as ET
import requests
from requests.auth import HTTPDigestAuth
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext
import pystray
from PIL import Image, ImageDraw

import conecction_dvr

AT_API_BASE_URL = "https://pf.api.apuestatotal.pe"
CONFIG_FILE = "config.json"

class Config:
    def __init__(self):
        self.config_data = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self.config_data = json.load(f)
            except Exception as e:
                print(f"[-] Error leyendo {CONFIG_FILE}: {e}")

        self.at_api_user = self.config_data.get("AT_API_USER") or "prevencion@apuestatotal.com"
        self.at_api_pass = self.config_data.get("AT_API_PASS") or "Password123*"
        self.dvr_user = self.config_data.get("DVR_USER", "admin")
        self.dvr_pass = self.config_data.get("DVR_PASS", "")
        self.dvr_ceco = self.config_data.get("DVR_CECO", "")
        self.dvr_ip = self.config_data.get("DVR_IP", "")
        self.sync_interval = self.config_data.get("SYNC_INTERVAL_MINUTES", 5)

    def save(self):
        self.config_data["AT_API_USER"] = self.at_api_user
        self.config_data["AT_API_PASS"] = self.at_api_pass
        self.config_data["DVR_USER"] = self.dvr_user
        self.config_data["DVR_PASS"] = self.dvr_pass
        self.config_data["DVR_CECO"] = self.dvr_ceco
        self.config_data["DVR_IP"] = self.dvr_ip
        self.config_data["SYNC_INTERVAL_MINUTES"] = self.sync_interval
        
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config_data, f, indent=4)
        except Exception as e:
            print(f"[-] Error guardando {CONFIG_FILE}: {e}")

    def is_valid(self):
        return all([self.at_api_user, self.at_api_pass, self.dvr_user, self.dvr_pass, self.dvr_ceco, self.dvr_ip])

class ApuestaTotalClient:
    def __init__(self, user, password):
        self.user = user
        self.password = password
        self.token = None

    def login(self):
        url = f"{AT_API_BASE_URL}/pf-cctv/v1/auth/login"
        payload = {"email": self.user, "password": self.password}
        try:
            resp = requests.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("access_token", data.get("token")) # Ajustar segun respuesta real
            if not self.token:
                # Intenta extraer de headers si aplica, pero usualmente esta en el body
                print("[!] Advertencia: No se encontro token en la respuesta de login.")
            print("[+] Login en AT API exitoso.")
            return True
        except Exception as e:
            print(f"[-] Error en Login AT API: {e}")
            return False

    def get_headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def post_recording_status(self, payload):
        url = f"{AT_API_BASE_URL}/pf-cctv/v1/dvr/recording-status"
        try:
            resp = requests.post(url, json=payload, headers=self.get_headers())
            resp.raise_for_status()
            print(f"[+] Recording status enviado correctamente.")
        except Exception as e:
            print(f"[-] Error enviando Recording Status: {e}")

    def post_storage_status(self, payload):
        url = f"{AT_API_BASE_URL}/pf-cctv/v1/dvr/storage-status"
        try:
            resp = requests.post(url, json=payload, headers=self.get_headers())
            resp.raise_for_status()
            print(f"[+] Storage status enviado correctamente.")
        except Exception as e:
            print(f"[-] Error enviando Storage Status: {e}")

    def post_event(self, payload):
        url = f"{AT_API_BASE_URL}/pf-cctv/v1/events-hv"
        try:
            resp = requests.post(url, json=payload, headers=self.get_headers())
            resp.raise_for_status()
            print(f"[+] Evento enviado correctamente: {payload.get('eventType')}")
        except Exception as e:
            print(f"[-] Error enviando Evento: {e}")

class HikvisionClient:
    def __init__(self, ip, user, password):
        self.base_url = f"http://{ip}"
        self.auth = HTTPDigestAuth(user, password)
        self.device_info = {}

    def fetch_device_info(self):
        try:
            resp = requests.get(f"{self.base_url}/ISAPI/System/deviceInfo", auth=self.auth, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            namespace = ""
            if "}" in root.tag:
                namespace = root.tag.split("}")[0] + "}"
                
            self.device_info['dvrName'] = root.find(f"{namespace}deviceName").text if root.find(f"{namespace}deviceName") is not None else "Unknown"
            self.device_info['dvrSerialNumber'] = root.find(f"{namespace}serialNumber").text if root.find(f"{namespace}serialNumber") is not None else "Unknown"
            self.device_info['dvrId'] = root.find(f"{namespace}deviceID").text if root.find(f"{namespace}deviceID") is not None else self.device_info['dvrSerialNumber']
            print(f"[+] DVR Info: {self.device_info['dvrName']} (SN: {self.device_info['dvrSerialNumber']})")
            return self.device_info
        except Exception as e:
            print(f"[-] Error obteniendo deviceInfo: {e}")
            return None

    def fetch_storage_status(self):
        try:
            resp = requests.get(f"{self.base_url}/ISAPI/ContentMgmt/Storage/hdd", auth=self.auth, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            namespace = ""
            if "}" in root.tag:
                namespace = root.tag.split("}")[0] + "}"
                
            storage_list = []
            for hdd in root.findall(f".//{namespace}hdd"):
                hd_no = int(hdd.find(f"{namespace}id").text) if hdd.find(f"{namespace}id") is not None else 0
                status = hdd.find(f"{namespace}status").text if hdd.find(f"{namespace}status") is not None else "unknown"
                capacity_mb = int(hdd.find(f"{namespace}capacity").text) if hdd.find(f"{namespace}capacity") is not None else 0
                free_space_mb = int(hdd.find(f"{namespace}freeSpace").text) if hdd.find(f"{namespace}freeSpace") is not None else 0
                hdd_type = hdd.find(f"{namespace}property").text if hdd.find(f"{namespace}property") is not None else "RW"
                
                # Convertir MB a Bytes (1024 * 1024 = 1048576)
                capacity = capacity_mb * 1048576
                free_space = free_space_mb * 1048576
                
                used_space = capacity - free_space
                usage_percent = int((used_space / capacity) * 100) if capacity > 0 else 0
                
                storage_list.append({
                    "hdNo": hd_no,
                    "status": status,
                    "hddType": hdd_type,
                    "volume": capacity,
                    "freeSpace": free_space,
                    "usedSpace": used_space,
                    "usagePercent": usage_percent
                })
            return storage_list
        except Exception as e:
            print(f"[-] Error obteniendo storageStatus: {e}")
            return []

    def fetch_track_ids(self):
        try:
            resp = requests.get(f"{self.base_url}/ISAPI/ContentMgmt/record/tracks", auth=self.auth, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
            track_ids = []
            for track in root.findall(f".//{ns}Track"):
                id_node = track.find(f"{ns}id")
                if id_node is not None:
                    track_ids.append(int(id_node.text))
            return track_ids
        except Exception as e:
            print(f"[-] Error obteniendo track IDs: {e}")
            return []

    def fetch_track_detail(self, track_id):
        try:
            resp = requests.get(f"{self.base_url}/ISAPI/ContentMgmt/record/tracks/{track_id}", auth=self.auth, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
            
            channel_node = root.find(f"{ns}Channel")
            channel = int(channel_node.text) if (channel_node is not None and channel_node.text is not None) else 0
            
            enable_node = root.find(f"{ns}Enable")
            enable = (enable_node.text.lower() == "true") if (enable_node is not None and enable_node.text is not None) else True
            
            src_desc = root.find(f"{ns}SrcDescriptor")
            src_type = ""
            src_channel = None
            if src_desc is not None:
                st_node = src_desc.find(f"{ns}SrcType")
                if st_node is not None and st_node.text is not None: src_type = st_node.text
                sc_node = src_desc.find(f"{ns}SrcChannel")
                if sc_node is not None and sc_node.text is not None: src_channel = int(sc_node.text)
                
            return {
                "track_id": track_id,
                "channel": channel,
                "enable": enable,
                "src_type": src_type,
                "src_channel": src_channel
            }
        except Exception as e:
            print(f"[-] Error obteniendo track detail para {track_id}: {e}")
            return None

    def search_last_recording(self, track_id):
        try:
            import uuid
            import datetime
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            start_time = (now_utc - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_time = (now_utc + datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            
            xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
            <CMSearchDescription>
              <searchID>{uuid.uuid4()}</searchID>
              <trackList>
                <trackID>{track_id}</trackID>
              </trackList>
              <timeSpanList>
                <timeSpan>
                  <startTime>{start_time}</startTime>
                  <endTime>{end_time}</endTime>
                </timeSpan>
              </timeSpanList>
              <maxResults>100</maxResults>
              <searchResultPostion>0</searchResultPostion>
              <metadataList>
                <metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor>
              </metadataList>
            </CMSearchDescription>"""
            
            resp = requests.post(f"{self.base_url}/ISAPI/ContentMgmt/search", auth=self.auth, data=xml_payload, headers={'Content-Type': 'application/xml'}, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
            
            end_times = []
            for et_node in root.findall(f".//{ns}endTime"):
                if et_node is not None and et_node.text is not None:
                    dt_str = et_node.text.replace("Z", "")
                    try:
                        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
                        end_times.append(dt)
                    except:
                        pass
                        
            if end_times:
                return max(end_times)
            return None
        except Exception as e:
            print(f"[-] Error buscando grabaciones para track {track_id}: {e}")
            return None

    def fetch_recording_status(self):
        try:
            # 1. Obtener canales (VideoInputs) para ver online status
            resp = requests.get(f"{self.base_url}/ISAPI/System/Video/inputs/channels", auth=self.auth, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            namespace = ""
            if "}" in root.tag:
                namespace = root.tag.split("}")[0] + "}"
                
            channels = []
            for ch in root.findall(f".//{namespace}VideoInputChannel"):
                id_node = ch.find(f"{namespace}id")
                ch_id = int(id_node.text) if (id_node is not None and id_node.text is not None) else 0
                
                name_node = ch.find(f"{namespace}name")
                name = name_node.text if (name_node is not None and name_node.text is not None) else f"Camera {ch_id}"
                
                enabled_node = ch.find(f"{namespace}videoInputEnabled")
                enabled_text = enabled_node.text if (enabled_node is not None and enabled_node.text is not None) else "false"
                
                res_desc_node = ch.find(f"{namespace}resDesc")
                res_desc = res_desc_node.text if (res_desc_node is not None and res_desc_node.text is not None) else ""
                
                is_online = (enabled_text.lower() == "true") and (res_desc.strip().upper() != "NO VIDEO")
                channels.append({"id": ch_id, "name": name, "is_online": is_online})
                
            # 2. Obtener Tracks para saber si tiene grabacion configurada
            track_ids = self.fetch_track_ids()
            track_map = {} # physical channel -> track_id
            for tid in track_ids:
                detail = self.fetch_track_detail(tid)
                if not detail or not detail["enable"]: continue
                
                is_local = (detail["src_type"].lower() == "local" if detail["src_type"] else (detail["src_channel"] is not None))
                if not is_local: continue

                
                phys_ch = detail["src_channel"] if detail["src_channel"] is not None else (detail["channel"] // 100 if detail["channel"] >= 100 else detail["channel"])
                track_map[phys_ch] = tid
                
            # 3. Mapear canales a tracks y buscar grabaciones
            statuses = []
            import datetime
            now_local = datetime.datetime.now()
            
            for ch in channels:
                ch_id = ch["id"]
                name = ch["name"]
                is_online = ch["is_online"]
                
                has_rec_conf = False
                is_recording = False
                last_rec_utc = None
                
                if is_online:
                    tid = track_map.get(ch_id)
                    if tid is not None:
                        has_rec_conf = True
                        last_rec_dt = self.search_last_recording(tid)
                        if last_rec_dt:
                            diff_mins = abs((now_local - last_rec_dt).total_seconds()) / 60.0
                            if diff_mins <= 5.0:
                                is_recording = True
                            
                            local_dt = last_rec_dt.astimezone()
                            last_rec_utc = local_dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                                
                statuses.append({
                    "channel": ch_id,
                    "cameraName": name,
                    "isOnline": is_online,
                    "hasRecordingConfigured": has_rec_conf,
                    "isRecording": is_recording,
                    "lastRecordingUtc": last_rec_utc
                })
                
            return statuses
        except Exception as e:
            print(f"[-] Error obteniendo recordingStatus: {e}")
            return []

    def stream_events(self, on_event_callback):
        url = f"{self.base_url}/ISAPI/Event/notification/alertStream"
        print(f"[*] Iniciando conexion al stream de eventos: {url}")
        try:
            with requests.get(url, auth=self.auth, stream=True, timeout=(15, None)) as resp:
                resp.raise_for_status()
                buffer = ""
                for line in resp.iter_lines(decode_unicode=True):
                    if line:
                        if isinstance(line, bytes):
                            line = line.decode('utf-8', errors='ignore')
                        buffer += line
                        if "</EventNotificationAlert>" in line:
                            try:
                                root = ET.fromstring(buffer)
                                namespace = ""
                                if "}" in root.tag:
                                    namespace = root.tag.split("}")[0] + "}"
                                    
                                event_type = root.find(f"{namespace}eventType").text if root.find(f"{namespace}eventType") is not None else "unknown"
                                event_state = root.find(f"{namespace}eventState").text if root.find(f"{namespace}eventState") is not None else ""
                                ch_id = root.find(f"{namespace}channelID").text if root.find(f"{namespace}channelID") is not None else "0"
                                
                                # Solo procesamos eventos activos o utiles
                                if event_state == "active" or not event_state:
                                    on_event_callback({
                                        "eventType": event_type,
                                        "channel": ch_id
                                    })
                            except ET.ParseError:
                                pass
                            buffer = ""
        except Exception as e:
            print(f"[-] Stream de eventos desconectado o error: {e}")

def get_current_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

def dvr_worker(config, stop_event):
    at_client = ApuestaTotalClient(config.at_api_user, config.at_api_pass)
    if not at_client.login():
        print("[-] Abortando ejecucion por fallo de login.")
        return

    hik_client = HikvisionClient(config.dvr_ip, config.dvr_user, config.dvr_pass)
    device_info = hik_client.fetch_device_info()
    if not device_info:
        print("[-] Abortando ejecucion, no se pudo contactar el DVR.")
        return

    print("[*] ¡Validación exitosa! Ejecutando en segundo plano...")
    
    def handle_event(event_data):
        event_payload = {
            "eventType": event_data["eventType"],
            "eventTime": get_current_utc(),
            "dvrName": device_info.get("dvrName", ""),
            "dvrSerialNumber": device_info.get("dvrSerialNumber", ""),
            "externalId": config.dvr_ceco,
            "cameraName": f"Camera {event_data.get('channel', '0')}",
            "status": "new",
            "observations": ""
        }
        at_client.post_event(event_payload)

    event_thread = threading.Thread(target=hik_client.stream_events, args=(handle_event,), daemon=True)
    event_thread.start()

    while not stop_event.is_set():
        print(f"\n[*] [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Recolectando status de grabacion y almacenamiento...")
        
        storage_list = hik_client.fetch_storage_status()
        if storage_list:
            storage_payload = {
                "dvrId": device_info.get("dvrId", ""),
                "storeCeco": config.dvr_ceco,
                "capturedAtUtc": get_current_utc(),
                "storageList": storage_list
            }
            at_client.post_storage_status(storage_payload)

        recording_list = hik_client.fetch_recording_status()
        if recording_list:
            recording_payload = {
                "dvrId": device_info.get("dvrId", ""),
                "storeCeco": config.dvr_ceco,
                "capturedAtUtc": get_current_utc(),
                "statuses": recording_list,
                "dvrName": device_info.get("dvrName", "")
            }
            at_client.post_recording_status(recording_payload)
            
        stop_event.wait(config.sync_interval * 60)

class RedirectText(object):
    def __init__(self, text_ctrl):
        self.output = text_ctrl
        self.queue = queue.Queue()
        self.update_me()

    def write(self, string):
        self.queue.put(string)

    def flush(self):
        pass

    def update_me(self):
        try:
            while True:
                string = self.queue.get_nowait()
                self.output.insert(tk.END, string)
                self.output.see(tk.END)
                self.output.update_idletasks()
        except queue.Empty:
            pass
        self.output.after(100, self.update_me)

class DvrAgentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Agente DVR ApuestaTotal")
        self.root.geometry("650x550")
        
        self.config = Config()
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.icon = None

        self.setup_ui()
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)

        if self.config.is_valid():
            self.start_agent()

    def setup_ui(self):
        form_frame = ttk.LabelFrame(self.root, text="Configuración")
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(form_frame, text="AT API User:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.ent_at_user = ttk.Entry(form_frame, width=25)
        self.ent_at_user.insert(0, self.config.at_api_user)
        self.ent_at_user.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(form_frame, text="AT API Pass:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.ent_at_pass = ttk.Entry(form_frame, width=25, show="*")
        self.ent_at_pass.insert(0, self.config.at_api_pass)
        self.ent_at_pass.grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(form_frame, text="DVR IP:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.ent_dvr_ip = ttk.Entry(form_frame, width=25)
        self.ent_dvr_ip.insert(0, self.config.dvr_ip)
        self.ent_dvr_ip.grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(form_frame, text="DVR CECO:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        self.ent_dvr_ceco = ttk.Entry(form_frame, width=25)
        self.ent_dvr_ceco.insert(0, self.config.dvr_ceco)
        self.ent_dvr_ceco.grid(row=1, column=3, padx=5, pady=2)
        
        ttk.Label(form_frame, text="DVR User:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.ent_dvr_user = ttk.Entry(form_frame, width=25)
        self.ent_dvr_user.insert(0, self.config.dvr_user)
        self.ent_dvr_user.grid(row=2, column=1, padx=5, pady=2)

        ttk.Label(form_frame, text="DVR Pass:").grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)
        self.ent_dvr_pass = ttk.Entry(form_frame, width=25, show="*")
        self.ent_dvr_pass.insert(0, self.config.dvr_pass)
        self.ent_dvr_pass.grid(row=2, column=3, padx=5, pady=2)

        ttk.Label(form_frame, text="Sync (min):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.ent_sync = ttk.Entry(form_frame, width=10)
        self.ent_sync.insert(0, str(self.config.sync_interval))
        self.ent_sync.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)

        self.btn_start = ttk.Button(form_frame, text="Guardar e Iniciar", command=self.save_and_start)
        self.btn_start.grid(row=3, column=3, sticky=tk.E, padx=5, pady=5)

        log_frame = ttk.LabelFrame(self.root, text="Logs del Agente")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.txt_log = scrolledtext.ScrolledText(log_frame, state='normal', height=15)
        self.txt_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.redirector = RedirectText(self.txt_log)
        sys.stdout = self.redirector
        sys.stderr = self.redirector
        
        print("-" * 50)
        print(" Agente DVR ApuestaTotal (Python)")
        print("-" * 50)

    def save_and_start(self):
        self.config.at_api_user = self.ent_at_user.get().strip() or "prevencion@apuestatotal.com"
        self.config.at_api_pass = self.ent_at_pass.get().strip() or "Password123*"
        self.config.dvr_ip = self.ent_dvr_ip.get().strip()
        self.config.dvr_user = self.ent_dvr_user.get().strip()
        self.config.dvr_pass = self.ent_dvr_pass.get().strip()
        self.config.dvr_ceco = self.ent_dvr_ceco.get().strip()
        try:
            self.config.sync_interval = int(self.ent_sync.get().strip())
        except ValueError:
            self.config.sync_interval = 5

        if not self.config.dvr_ip:
            print("[*] DVR IP vacío. Buscando DVR en la red local...")
            def search_dvr():
                devices = conecction_dvr.discover_hikvision(timeout=3)
                if devices:
                    d_ip = devices[0]['ip']
                    d_port = devices[0].get('http_port', '80')
                    ip_found = f"{d_ip}:{d_port}" if d_port and d_port != '80' else d_ip
                    print(f"[+] DVR encontrado en: {ip_found}")
                    self.root.after(0, lambda: self.ent_dvr_ip.insert(0, ip_found))
                    self.config.dvr_ip = ip_found
                    self.config.save()
                    if self.config.is_valid():
                        self.start_agent()
                else:
                    print("[-] No se encontró DVR automáticamente. Ingrese IP manualmente.")
            threading.Thread(target=search_dvr, daemon=True).start()
            return

        self.config.save()
        if self.config.is_valid():
            self.start_agent()
        else:
            print("[-] Por favor complete todos los campos requeridos (Pass, CECO, etc).")

    def start_agent(self):
        self.btn_start.config(state=tk.DISABLED)
        if self.worker_thread and self.worker_thread.is_alive():
            print("[!] El agente ya está corriendo.")
            return
            
        print("[*] Iniciando el worker en segundo plano...")
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self.run_dvr_worker, daemon=True)
        self.worker_thread.start()

    def run_dvr_worker(self):
        try:
            dvr_worker(self.config, self.stop_event)
        except Exception as e:
            print(f"\n[!] Error critico en el agente: {e}")
        finally:
            self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))

    def create_image(self):
        width = 64
        height = 64
        color1 = (0, 0, 0)
        color2 = (255, 255, 255)
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle((width // 4, height // 4, width * 3 // 4, height * 3 // 4), fill=color2)
        return image

    def hide_window(self):
        self.root.withdraw()
        image = self.create_image()
        menu = pystray.Menu(
            pystray.MenuItem('Mostrar', self.show_window, default=True),
            pystray.MenuItem('Salir', self.quit_window)
        )
        self.icon = pystray.Icon("dvr_agent", image, "DVR Agent AT", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def show_window(self, icon, item):
        self.icon.stop()
        self.root.after(0, self.root.deiconify)

    def quit_window(self, icon, item):
        self.icon.stop()
        self.stop_event.set()
        self.root.destroy()
        os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = DvrAgentApp(root)
    root.mainloop()
