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
    
    consecutive_in_progress = 0
    
    while True:
        try:
            # 1. Rychlý skener (2 vteřiny)
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=2.0)
            
            if device:
                print("Nalezeno! Okamžitě navazuji spojení...")
                publish_status("CONNECTING")
                
                # 2. BLESKOVÉ PŘIPOJENÍ - Bez jakýchkoliv pauz!
                async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=7.0) as client_ble:
                    print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                    publish_status("READY") 
                    consecutive_in_progress = 0 # Vynulujeme počítadlo chyb po úspěšném připojení
                    
                    await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    while client_ble.is_connected:
                        await asyncio.sleep(0.5)
                
                # 3. Odpojení
                print("Spojení ukončeno, čekám 0.5s...")
                await asyncio.sleep(0.5)
                
            else:
                # Ovladač spí
                await asyncio.sleep(0.2)
                
        except Exception as e:
            error_msg = str(e)
            print(f"Výpadek: {error_msg}")
            
            if "In Progress" in error_msg:
                # Připojení se zaseklo na straně Linuxu
                print("Připojení se zaseklo (In Progress), čekám...")
                await asyncio.sleep(2.0)
                consecutive_in_progress += 1
            elif "br-connection-canceled" in error_msg:
                # U této chyby je nejlepší zkusit to hned znovu, nečekat
                await asyncio.sleep(0.2)
            elif "discover services" in error_msg:
                # Připojilo se to, ale ESP32 hned usnulo nebo spadlo
                await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(1.0)
            
            # OPRAVDOVÝ TVRDÝ RESTART ADAPTÉRU
            # Pokud se BlueZ zasekne ve smyčce "In Progress", vypneme a zapneme samotný Bluetooth
            if consecutive_in_progress >= 2:
                print("!!! BlueZ modul je zcela zaseknutý. Provádím restart napájení Bluetooth...")
                try:
                    # Vypne Bluetooth rádio
                    subprocess.run(['bluetoothctl', 'power', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(1.0)
                    # Zapne Bluetooth rádio
                    subprocess.run(['bluetoothctl', 'power', 'on'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(2.0)
                except Exception as ex:
                    print(f"Nepodařilo se restartovat Bluetooth: {ex}")
                
                consecutive_in_progress = 0 # Vynulujeme počítadlo po restartu

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
