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
    print(f"--- SPUŠTĚN REŽIM PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    consecutive_errors = 0
    
    while True:
        try:
            # 1. Hledáme ovladač ve vzduchu (obcházíme paměťovou cache Linuxu)
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=3.0)
            
            if device:
                print(">>> Ovladač nalezen ve vzduchu! <<<")
                
                # ZLATÉ PRAVIDLO: Po skenování potřebuje BlueZ modul vteřinu na oddech,
                # jinak spojení okamžitě spadne na 'br-connection-canceled'.
                await asyncio.sleep(1.0) 
                
                publish_status("CONNECTING")
                
                # 2. Klasické obousměrné spojení (požadavek vedoucího)
                # Timeout nastaven na 10 sekund pro dostatek času na načtení služeb
                async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=10.0) as client_ble:
                    print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                    publish_status("READY") 
                    consecutive_errors = 0 # Úspěšné spojení = nulujeme chyby
                    
                    # Registrace příjmu dat
                    await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    # Držíme spojení aktivní (dokud se ovladač sám neuspí)
                    while client_ble.is_connected:
                        await asyncio.sleep(0.5)
                
                # Pokud se dostaneme sem, spojení bylo korektně ukončeno (ESP32 usnulo)
                print("Spojení korektně ukončeno. Čekám na uvolnění portů...")
                await asyncio.sleep(1.0)
                
            else:
                # Ovladač zrovna spí, nebudeme spamovat konzoli
                await asyncio.sleep(0.5)
                
        except Exception as e:
            error_msg = str(e)
            print(f"Výpadek spojení: {error_msg}")
            
            # Pokud se BlueZ zasekne na "In Progress" (typický neduh RPi), 
            # odstřelíme konkrétní zaseknuté spojení z mezipaměti.
            if "In Progress" in error_msg or "br-connection-canceled" in error_msg:
                print("Uklízím zablokovanou paměť Bluetooth modulu...")
                subprocess.run(['bluetoothctl', 'disconnect', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await asyncio.sleep(2.0)
                consecutive_errors += 1
            else:
                await asyncio.sleep(1.0)
            
            # Pokud se systém zacyklí úplně, provedeme "tvrdý" restart rádiového adaptéru
            if consecutive_errors >= 4:
                print("!!! BlueZ modul je tvrdě zacyklený. Provádím restart napájení Bluetooth...")
                try:
                    subprocess.run(['bluetoothctl', 'power', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(1.5)
                    subprocess.run(['bluetoothctl', 'power', 'on'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(2.0)
                except Exception as ex:
                    print(f"Nepodařilo se restartovat Bluetooth: {ex}")
                
                consecutive_errors = 0

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
