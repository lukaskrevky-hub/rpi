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
    print(f"--- SPUŠTĚN SNIPER REŽIM 2.0 (ČISTÁ DATA) NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            device_event = asyncio.Event()
            target_device = None

            def detection_callback(device, advertisement_data):
                nonlocal target_device
                # Reagujeme POUZE ve chvíli, kdy fyzicky dorazí paket z naší MAC adresy
                if device.address.lower() == TARGET_MAC.lower():
                    target_device = device
                    device_event.set()

            # 1. Nasloucháme POUZE živým datům, ignorujeme Linuxovou mezipaměť (cache)
            async with BleakScanner(detection_callback):
                await device_event.wait()
                
            # Pokud jsme zde, ESP32 fyzicky vyslalo čerstvý paket PRÁVĚ TEĎ.
            publish_status("CONNECTING")
            
            # Mikro-pauza pro bezpečné uvolnění antény po vypnutí skeneru
            await asyncio.sleep(0.3)
            
            # 2. Bleskové připojení k čerstvě ověřenému objektu
            async with BleakClient(target_device, disconnected_callback=disconnected_callback, timeout=5.0) as client_ble:
                publish_status("READY") 
                print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení, dokud ho ESP32 (po 30s nečinnosti) samo neukončí
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Odpojeno ESP32 modulem
            publish_status("SLEEP")
            await asyncio.sleep(0.5)
            
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
