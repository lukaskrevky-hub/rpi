import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys
import subprocess

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

# --- SNIPER LOGIKA (Limitní příkaz) ---
target_device = None
device_found_event = asyncio.Event()

def detection_callback(device, advertisement_data):
    """Tento callback se spustí, jakmile skener cokoliv uslyší."""
    global target_device
    if device.address.lower() == TARGET_MAC.lower():
        target_device = device
        device_found_event.set() # Odpálíme událost pro připojení

async def connect_and_listen():
    global target_device
    print(f"--- SPUŠTĚN SNIPER REŽIM NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    # Rychlý úklid před spuštěním
    subprocess.run(['bluetoothctl', 'disconnect', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Skener navážeme na náš detekční callback
    scanner = BleakScanner(detection_callback)
    
    while True:
        try:
            # 1. PASIVNÍ NASLOUCHÁNÍ
            # Zapneme skener a program se zde zastaví. Čeká donekonečna s nulovou zátěží CPU,
            # dokud se nespustí 'device_found_event'.
            await scanner.start()
            await device_found_event.wait()
            device_found_event.clear()
            
            publish_status("CONNECTING")
            
            # 2. UVOLNĚNÍ ANTÉNY
            # Naprosto kritický krok! Vypneme skener dřív, než se pokusíme připojit.
            # Tímto zmizí chyby In Progress a br-connection-canceled.
            await scanner.stop()
            await asyncio.sleep(0.5) # Dáme modulu půl vteřiny na přechod do režimu připojování
            
            # 3. BLESKOVÉ PŘIPOJENÍ
            async with BleakClient(target_device, timeout=10.0) as client_ble:
                publish_status("READY") 
                print("\n+++ PŘIPOJENO! Ovladač je aktivní. +++")
                
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení aktivní
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
            # Jakmile se ESP32 uspí
            print("--- Ovladač usnul ---")
            publish_status("SLEEP")
            
        except Exception as e:
            error_msg = str(e)
            print(f"   [Chyba] {error_msg}")
            publish_status("SLEEP")
            
            # Pojistka: Pokud spojení spadne, musíme mít jistotu, že je skener vypnutý, 
            # než se smyčka rozběhne znovu.
            try:
                await scanner.stop()
            except:
                pass
            
            # Rychlý úklid zombie spojení
            if "br-connection-canceled" in error_msg or "discover services" in error_msg:
                subprocess.run(['bluetoothctl', 'disconnect', TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)
