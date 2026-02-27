import asyncio
from bleak import BleakClient, BleakError
import paho.mqtt.client as mqtt
import sys

# ==========================================
# VAŠE ZJIŠTĚNÁ MAC ADRESA
TARGET_MAC = "10:06:1C:B5:A7:36"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# MQTT Konfigurace
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"  # <--- NOVÉ: Téma pro stav

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
    """Odeslání stavu do MQTT (retain=True aby si to web načetl i po refresh)"""
    print(f"STAV -> {status}") 
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    """Zpracování dat přijatých z ESP32."""
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    """Zavolá se, když se ESP32 odpojí (usne)."""
    print(">>> Ztráta spojení (Joystick usnul nebo je mimo dosah).")
    publish_status("SLEEP")

# --- HLAVNÍ SMYČKA PRO PŘIPOJENÍ ---

async def connect_and_listen():
    print(f"--- SPUŠTĚN DIRECT CONNECT NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            print(f"Čekám na probuzení joysticku ({TARGET_MAC})...")
            
            # timeout=15.0: RPi bude 15 sekund čekat na této adrese.
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=15.0) as client:
                
                # Pokud jsme se dostali sem, handshaking začal
                publish_status("CONNECTING") 
                print("Navazuji spojení...")
                
                # Zapneme notifikace
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                print("PŘIPOJENO! Ovladač je aktivní.")
                publish_status("READY") 
                
                # Smyčka udržující spojení
                while client.is_connected:
                    await asyncio.sleep(0.5)
            
            # Zde se kód dostane po odpojení
            
        except Exception as e:
            # Pokud se připojení nepovede (joystick spí), je to OK.
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)

