import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

# ==========================================
# CÍLOVÁ MAC ADRESA
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

current_status = ""

def publish_status(status):
    global current_status
    if current_status != status:
        print(f"STAV -> {status}") 
        client.publish(TOPIC_STATUS, status, retain=True)
        current_status = status

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    client.publish(MQTT_TOPIC, command)

async def connect_and_listen():
    print(f"--- SPUŠTĚN KLIDNÝ REŽIM (BUY & HOLD) NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # 1. Hledáme ovladač (tichý sken)
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=3.0)
            
            if not device:
                # Ovladač spí, tiše čekáme dál
                await asyncio.sleep(0.5)
                continue
                
            publish_status("CONNECTING")
            
            # 2. ZLATÁ PAUZA: Než zavelíme k připojení, necháme Linux vteřinu vydechnout
            await asyncio.sleep(1.0)
            
            # 3. Samotné připojení
            async with BleakClient(device, timeout=10.0) as client_ble:
                publish_status("READY") 
                print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení, dokud ESP32 po 30s nečinnosti samo neusne
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Jakmile se ESP32 korektně odpojí
            print("--- Ovladač usnul ---")
            publish_status("SLEEP")
            await asyncio.sleep(1.0)
            
        except Exception as e:
            error_msg = str(e)
            
            # Absorpce šumu. Pokud je to In Progress, Linux prostě zrovna pracuje.
            # ŽÁDNÉ ZRUŠENÍ, ŽÁDNÝ RESTART. Prostě počkáme 2 vteřiny.
            if "In Progress" in error_msg:
                await asyncio.sleep(2.0)
            elif "br-connection-canceled" in error_msg:
                # Spojení spadlo, zkusíme ho v další smyčce znovu načíst
                await asyncio.sleep(1.0)
            elif "was not found" not in error_msg:
                # Ostatní drobné chyby tiše vypíšeme, ale nepanikaříme
                print(f"   [Šum na trhu] {error_msg}")
                await asyncio.sleep(1.0)
            else:
                await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
