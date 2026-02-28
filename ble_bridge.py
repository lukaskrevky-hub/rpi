import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

# ==========================================
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

def disconnected_callback(client_ble):
    pass # Ignorujeme spam z Linuxu, stav vyřeší smyčka níže

async def connect_and_listen():
    print(f"--- SPUŠTĚN BLESKOVÝ REŽIM (S FILTREM DUCHŮ) NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            # 1. Bleskový sken (max 1.0s). 
            # Pokud ESP32 vysílá, vrátí výsledek OKAMŽITĚ a nečeká!
            # Tím ověříme, že zařízení fyzicky existuje a vyhneme se Linuxovým falešným spojením.
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=1.0)
            
            if not device:
                # Ovladač opravdu spí, bleskově zkusíme znovu
                await asyncio.sleep(0.1)
                continue
                
            # Pokud jsme zde, zařízení 100% fyzicky vysílá
            publish_status("CONNECTING")
            
            # 2. Připojujeme se k prověřenému objektu 'device' (NE k textu)
            async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=5.0) as client_ble:
                publish_status("READY") 
                print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení, dokud ho ESP32 (po 30s nečinnosti) samo neukončí
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Odpojeno ESP32 modulem
            publish_status("SLEEP")
            await asyncio.sleep(0.1)
            
        except Exception as e:
            # Drobný šum ignorujeme a jedeme dál
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
