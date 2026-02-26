import asyncio
from bleak import BleakScanner
import paho.mqtt.client as mqtt
import sys
import time

# --- KONFIGURACE ---
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"

# --- MQTT SETUP ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    
    # Protože v Beacon režimu malina neustále poslouchá, 
    # pro web to znamená, že je systém neustále "READY"
    client.publish(TOPIC_STATUS, "READY", retain=True)
    print("MQTT připojeno. Systém je v režimu POHOTOVOSTI.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# Proměnné proti spamu (aby jedno pohnutí páčkou nevyvolalo 10 kliknutí v menu)
last_cmd = None
last_time = 0

# --- FUNKCE PRO ZPRACOVÁNÍ TOHO, CO LÉTÁ VZDUCHEM ---
def detection_callback(device, advertisement_data):
    global last_cmd, last_time
    
    # Podíváme se na jméno vysílaného Bluetooth zařízení
    name = advertisement_data.local_name or device.name
    
    # Pokud jméno začíná na "JOY:", je to náš ovladač!
    if name and name.startswith("JOY:"):
        cmd = name.split(":")[1] # Vyřízneme z "JOY:UP" jen to "UP"
        
        # Debounce logika: ESP32 křičí paket velmi rychle za sebou. 
        # Zahodíme duplikáty, pokud přišly do 0.4 vteřiny.
        current_time = time.time()
        if cmd == last_cmd and (current_time - last_time) < 0.4:
            return 
            
        last_cmd = cmd
        last_time = current_time
        
        print(f"BLESKOVÝ PŘÍJEM: {cmd}")
        client.publish(MQTT_TOPIC, cmd)


# --- HLAVNÍ SMYČKA SKENERU ---
async def main():
    print("Startuji BEACON Scanner... Čekám na povely z joysticku.")
    
    # Nastavíme skener s naším odchytávacím callbackem
    scanner = BleakScanner(detection_callback)
    await scanner.start()
    
    try:
        # Necháme program běžet donekonečna
        while True:
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
    finally:
        await scanner.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji...")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        client.loop_stop()
        sys.exit(0)
