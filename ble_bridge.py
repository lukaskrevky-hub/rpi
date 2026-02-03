import asyncio
from bleak import BleakClient, BleakError
import paho.mqtt.client as mqtt
import sys

# ==========================================
# VAŠE ZJIŠTĚNÁ MAC ADRESA
TARGET_MAC = "38:18:2B:B3:80:8E"
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

# --- CALLBACK FUNKCE ---

def notification_handler(sender, data):
    try:
        command = data.decode('utf-8').strip()
        # print(f"--> Přijato: {command}")
        client.publish(MQTT_TOPIC, command)
    except Exception as e:
        print(f"Chyba dat: {e}")

def disconnected_callback(client):
    print("Joystick odpojen (Callback).")
    publish_status("SLEEP") # <--- NOVÉ: Hned hlásíme, že spíme

# --- HLAVNÍ SMYČKA ---

async def main():
    print(f"Startuji Direct Connect na {TARGET_MAC}...")
    publish_status("SLEEP") # Výchozí stav po restartu
    
    while True:
        try:
            print(f"Čekám na probuzení joysticku ({TARGET_MAC})...")
            
            # Před pokusem o připojení můžeme hlásit, že systém čeká (nebo se připojuje)
            # Zde dáme CONNECTING těsně před pokus, aby to na webu probliklo žlutě
            
            # timeout=15.0: RPi bude 15 sekund čekat na této adrese.
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=15.0) as client:
                
                # Pokud jsme se dostali sem, handshaking začal
                publish_status("CONNECTING") 
                print("Navazuji spojení...")
                
                # Zapneme notifikace
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                print("PŘIPOJENO! Ovladač je aktivní.")
                publish_status("READY") # <--- NOVÉ: Zelená na webu!
                
                # Smyčka udržující spojení
                while client.is_connected:
                    await asyncio.sleep(0.5)
            
            # Zde se kód dostane po odpojení

        except Exception as e:
            # Pokud se připojení nepovede (joystick spí), je to OK.
            # Ujistíme se, že stav je SLEEP
            # publish_status("SLEEP") 
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        client.loop_stop()
