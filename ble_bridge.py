import asyncio
from bleak import BleakClient, BleakError
import paho.mqtt.client as mqtt
import sys

# ==========================================
# OPRAVA: SPRÁVNÁ MAC ADRESA
TARGET_MAC = "10:06:1C:B5:A7:34"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# MQTT Konfigurace
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status" 

# --- MQTT SETUP ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- POMOCNÉ FUNKCE ---

def publish_status(status):
    """Odeslání stavu do MQTT"""
    print(f"STAV -> {status}") 
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    """Zpracování dat přijatých z ESP32."""
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    """Zavolá se, když se ESP32 odpojí (usne)."""
    print(">>> Ztráta spojení (Joystick usnul).")
    publish_status("SLEEP")

# --- HLAVNÍ SMYČKA PRO PŘIPOJENÍ ---

async def connect_and_listen():
    print(f"--- SPUŠTĚN DIRECT CONNECT NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            print(f"Čekám na probuzení joysticku ({TARGET_MAC})...")
            
            # OPRAVA TIMEOUTU: 5 vteřin je ideální balanc. Malina se nezamrazí 
            # na 15 vteřin, když ESP spí, ale reaguje svižně.
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=5.0) as client:
                
                publish_status("CONNECTING") 
                print("Navazuji spojení...")
                
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                print("PŘIPOJENO! Ovladač je aktivní.")
                publish_status("READY") 
                
                # Udržujeme spojení
                while client.is_connected:
                    await asyncio.sleep(0.5)
            
        except Exception as e:
            # Rychlý spánek a nový pokus, pokud ESP zrovna nebylo dostupné
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
