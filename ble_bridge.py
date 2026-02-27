import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys
import subprocess

# ==========================================
# CÍLOVÁ MAC ADRESA (Potvrzená Bluetooth adresa ESP32)
TARGET_MAC = "10:06:1C:B5:A7:36"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status" 

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# Globální paměť pro zamezení duplicitních výpisů (Filtrace šumu)
current_status = ""

def publish_status(status):
    global current_status
    # Zprávu odešleme pouze tehdy, pokud se stav SKUTEČNĚ změnil
    if current_status != status:
        print(f"STAV -> {status}") 
        client.publish(TOPIC_STATUS, status, retain=True)
        current_status = status

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client_ble):
    # Callback se v Linuxu často zblázní a volá se 10x po sobě. 
    # Díky naší funkci publish_status se ale vypíše jen jednou.
    publish_status("SLEEP")

async def connect_and_listen():
    print(f"--- SPUŠTĚN OPTIMALIZOVANÝ REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    consecutive_errors = 0
    
    while True:
        try:
            # 1. Hledáme ovladač ve vzduchu (slouží jen jako rychlý radar)
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=2.0)
            
            if device:
                publish_status("CONNECTING")
                
                # 2. Okamžité připojení! 
                # Předáváme přímo TARGET_MAC místo objektu 'device', což na RPi eliminuje chybu "discover services"
                async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=6.0) as client_ble:
                    
                    publish_status("READY") 
                    print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                    consecutive_errors = 0 # Úspěšné spojení = nulujeme chyby
                    
                    await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    while client_ble.is_connected:
                        await asyncio.sleep(0.5)
                
                # Po korektním odpojení
                print("Spojení korektně ukončeno.")
                publish_status("SLEEP")
                await asyncio.sleep(0.5)
                
            else:
                # Ovladač zrovna spí, pošleme SLEEP (vypíše se jen pokud se stav změnil)
                publish_status("SLEEP")
                await asyncio.sleep(0.2)
                
        except Exception as e:
            error_msg = str(e)
            
            # Nebudeme spamovat terminál drobnými chybami
            if "was not found" not in error_msg and "EOFError" not in error_msg:
                print(f"Výpadek spojení: {error_msg}")
            
            publish_status("SLEEP")
            
            # Rychlý úklid po zablokovaném spojení
            if "In Progress" in error_msg or "br-connection-canceled" in error_msg:
                subprocess.run(['bluetoothctl', 'disconnect', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await asyncio.sleep(0.5)
                consecutive_errors += 1
            elif "discover services" in error_msg:
                # Pokud načítání služeb spadne, zkusíme to hned znovu, ESP32 má 30s timeout
                await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(0.5)
            
            # Tvrdý restart adaptéru při velkém zacyklení
            if consecutive_errors >= 4:
                print("!!! BlueZ modul je tvrdě zacyklený. Provádím restart napájení Bluetooth...")
                try:
                    subprocess.run(['bluetoothctl', 'power', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(1.0)
                    subprocess.run(['bluetoothctl', 'power', 'on'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(1.5)
                except Exception:
                    pass
                consecutive_errors = 0

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
