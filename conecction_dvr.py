import socket
import uuid
import xml.etree.ElementTree as ET
import time
from typing import List, Dict, Optional

SADP_IP = "239.255.255.250"
SADP_PORT = 37020

def get_local_interfaces() -> List[str]:
    interfaces = set()
    try:
        # metodo 1: Obtener hostname e IPs asociadas
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                interfaces.add(ip)
    except Exception:
        pass

    try:
        # metodo 2: Conectar a un socket UDP externo (dummy) para obtener la IP default
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        interfaces.add(ip)
        s.close()
    except Exception:
        pass

    if not interfaces:
        return ["0.0.0.0"] # Fallback

    return list(interfaces)

def parse_sadp_response(xml_data: bytes) -> Optional[Dict[str, str]]:
    try:
        root = ET.fromstring(xml_data)
        
        # validar que sea un paquete de respuesta SADP
        if root.tag not in ["ProbeMatch", "Probe"]: 
            return None

        # helper seguro para extraer texto
        def get_text(path):
            node = root.find(path)
            return node.text if node is not None else "N/A"

        return {
            "ip": get_text(".//IPv4Address"),
            "ipv6": get_text(".//IPv6Address"),
            "port": get_text(".//CommandPort"),
            "http_port": get_text(".//HttpPort"),
            "mac": get_text(".//MAC"),
            "model": get_text(".//DeviceModel"),
            "serial": get_text(".//DeviceSerialNo"),
            "version": get_text(".//SoftwareVersion"),
            "activated": "Yes" if get_text(".//Activated") == "true" else "No",
            "gateway": get_text(".//DefaultGateway"),
            "subnet_mask": get_text(".//SubnetMask"),
            "boot_time": get_text(".//BootTime")
        }
    except ET.ParseError:
        return None
    except Exception as e:
        # print(f"Error parsing XML: {e}")
        return None

def discover_hikvision(timeout: int = 2) -> List[Dict[str, str]]:
    found_devices = {} # usar dict para evitar duplicados por MAC
    interfaces = get_local_interfaces()
    
    xml_payload = (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<Probe>'
        f'<Uuid>{str(uuid.uuid4()).upper()}</Uuid>'
        f'<Types>inquiry</Types>'
        f'</Probe>'
    ).encode('utf-8')

    print(f"[*] Iniciando escaneo SADP en interfaces: {', '.join(interfaces)} ...")

    for interface_ip in interfaces:
        sock = None
        try:
            # configurar socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.settimeout(timeout)
            
            # permitir reuso de direccion
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except:
                pass
                
            # bind a la interfaz especifica para escuchar respuestas
            try:
                sock.bind((interface_ip, 0)) # Puerto aleatorio
            except OSError:
                # si falla bindear a IP especifica, intentar default
                if interface_ip != "0.0.0.0":
                    continue 

            # configurar TTL y Multicast
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            
            # enviar multicast desde esta interfaz
            sock.sendto(xml_payload, (SADP_IP, SADP_PORT))
            
            start_time = time.time()
            while (time.time() - start_time) < timeout:
                try:
                    data, addr = sock.recvfrom(4096)
                    device_info = parse_sadp_response(data)
                    
                    if device_info and device_info.get("mac"):
                        mac = device_info["mac"]
                        if mac not in found_devices:
                            found_devices[mac] = device_info
                            # opcional: imprimir inmediatamente al encontrar para feedback visual
                            # print(f"[+] Nuevo dispositivo: {device_info['ip']} ({device_info['model']})")
                except socket.timeout:
                    break
                except OSError:
                    break
                    
        except Exception as e:
            print(f"[!] Error escaneando interfaz {interface_ip}: {e}")
        finally:
            if sock:
                sock.close()

    return list(found_devices.values())

if __name__ == "__main__":
    print("-" * 60)
    print(" Buscador de Dispositivos Hikvision (Python SADP)")
    print("-" * 60)
    
    devices = discover_hikvision(timeout=3)
    
    if devices:
        print(f"\n[+] Se encontraron {len(devices)} dispositivos:")
        for i, dev in enumerate(devices, 1):
            print(f"\nDispositivo #{i}")
            print(f"  Modelo   : {dev['model']}")
            print(f"  IP Addr  : {dev['ip']}")
            print(f"  MAC      : {dev['mac']}")
            print(f"  Serial   : {dev['serial']}")
            print(f"  Version  : {dev['version']}")
            print(f"  Status   : {'Activo' if dev['activated'] == 'Yes' else 'Inactivo'}")
            print(f"  Http Port: {dev['http_port']}")
    else:
        print("\n[-] No se encontraron dispositivos Hikvision.")
