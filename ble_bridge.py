import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys
import subprocess

# ==========================================
# CÍLOVÁ MAC ADRESA (Potvrzená)
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

def publish_status(status):
    print(f"STAV -> {status}") 
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    print(">>> Ztráta spojení (Joystick usnul nebo byl výpadek).")
    publish_status("SLEEP")

async def connect_and_listen():
    print(f"--- SPUŠTĚN STABILNÍ REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    consecutive_errors = 0
    
    while True:
        try:
            # 1. Rychlý skener (2 vteřiny)
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=2.0)
            
            if device:
                print(">>> Ovladač nalezen ve vzduchu! <<<")
                
                # ZLATÝ KOMPROMIS: 0.5s pauza. 
                # Zabrání chybě 'br-connection-canceled', ale není tak dlouhá, aby ESP32 usnulo.
                await asyncio.sleep(0.5) 
                
                publish_status("CONNECTING")
                
                # 2. Připojení
                async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=10.0) as client_ble:
                    print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                    publish_status("READY") 
                    consecutive_errors = 0 # Vynulujeme počítadlo chyb po úspěšném připojení
                    
                    await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    # Držíme spojení aktivní
                    while client_ble.is_connected:
                        await asyncio.sleep(0.5)
                
                # 3. Odpojení
                print("Spojení korektně ukončeno. Čekám 1s na uvolnění portů...")
                await asyncio.sleep(1.0)
                
            else:
                # Ovladač spí
                await asyncio.sleep(0.2)
                
        except Exception as e:
            error_msg = str(e)
            print(f"Výpadek spojení: {error_msg}")
            
            if "In Progress" in error_msg:
                # Modul se zasekl na straně Linuxu
                print("Modul je zaneprázdněn (In Progress), čekám 2 vteřiny...")
                await asyncio.sleep(2.0)
                consecutive_errors += 1
            elif "br-connection-canceled" in error_msg:
                # Systém zrušil proces, zkusíme to po krátké chvíli znovu
                print("Spojení zrušeno systémem, zkouším to za chvíli znovu...")
                await asyncio.sleep(0.5)
                consecutive_errors += 1
            elif "discover services" in error_msg:
                # ESP32 pravděpodobně usnulo hned po spojení
                print("Nepodařilo se načíst služby (ESP32 pravděpodobně usnulo).")
                await asyncio.sleep(1.0)
            else:
                await asyncio.sleep(1.0)
            
            # OPRAVDOVÝ TVRDÝ RESTART ADAPTÉRU
            if consecutive_errors >= 3:
                print("!!! BlueZ modul je zacyklený. Provádím restart napájení Bluetooth...")
                try:
                    subprocess.run(['bluetoothctl', 'power', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(1.5)
                    subprocess.run(['bluetoothctl', 'power', 'on'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(2.0)
                except Exception as ex:
                    print(f"Nepodařilo se restartovat Bluetooth: {ex}")
                
                consecutive_errors = 0 # Vynulujeme počítadlo po restartu

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
