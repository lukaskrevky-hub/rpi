import asyncio
from bleak import BleakClient, BleakError
import paho.mqtt.client as mqtt
import sys

# ==========================================
# VAŠE MAC ADRESA
TARGET_MAC = "38:18:2B:B3:80:8E"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"

# --- MQTT SETUP ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print(f"MQTT připojeno k {MQTT_BROKER}")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- FUNKCE ---

def publish_status(status):
    print(f"STAV -> {status}")
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    try:
        cmd = data.decode('utf-8').strip()
        # print(f"PŘIJATO: {cmd}") # Odkomentujte pro debug
        client.publish(MQTT_TOPIC, cmd)
    except:
        pass

def disconnected_callback(client):
    print("Odpojeno (Joystick usnul).")
    publish_status("SLEEP")

# --- HLAVNÍ SMYČKA ---

async def main():
    print(f"Startuji Bridge pro {TARGET_MAC}...")
    publish_status("SLEEP")
    
    while True:
        try:
            print(f"Čekám na signál od {TARGET_MAC}...")
            
            # timeout=20.0: Dlouhé čekání na probuzení
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=20.0) as ble:
                print("PŘIPOJENO!")
                publish_status("CONNECTING")
                
                await ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Pokud jsme došli sem, vše funguje
                publish_status("READY")
                
                # Smyčka udržující spojení
                while ble.is_connected:
                    await asyncio.sleep(1.0)
            
        except Exception as e:
            # Ignorujeme timeouty (joystick spí)
            # print(f"Info: {e}")
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        client.loop_stop()
