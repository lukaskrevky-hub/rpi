import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"

# UUID musí přesně odpovídat tomu v ESP32
CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
TARGET_NAME = "ESP-JOY"

# --- MQTT Setup ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- Zpracování příchozích dat ---
def notification_handler(sender, data):
    cmd = data.decode('utf-8')
    print(f"PŘIJATO BLE: {cmd}")
    client.publish(MQTT_TOPIC, cmd)

# --- Hlavní asynchronní smyčka ---
async def main():
    print("Startuji Ultra-Fast Hybrid Bridge...")
    client.publish(TOPIC_STATUS, "READY", retain=True)

    while True:
        try:
            # 1. Čekáme na záblesk zařízení - Rychlé vyhledání pomocí optimalizované funkce
            print(f"Čekám na probuzení joysticku ({TARGET_NAME})...")
            
            # Timeout je schválně velký (hodina), malina prostě vyčkává na pozadí
            device = await BleakScanner.find_device_by_name(TARGET_NAME, timeout=3600.0)

            if device:
                print("Joystick se probudil! Bleskově se připojuji...")
                
                # 2. Bleskové připojení k nalezenému zařízení
                async with BleakClient(device) as ble_client:
                    print("Spojení navázáno! Čekám na povely (15s Hybrid režim)...")
                    
                    # 3. Přihlásíme se k odběru dat (od této chvíle je spojení okamžité)
                    await ble_client.start_notify(CHAR_UUID, notification_handler)
                    
                    # 4. Držíme skript ve smyčce, dokud je ESP32 připojené (těch 15 vteřin)
                    while ble_client.is_connected:
                        await asyncio.sleep(0.1)
                        
                    print("Joystick ukončil spojení a usnul. Jdu znovu skenovat.")
                    
        except Exception as e:
            # Ignorujeme drobné chyby (např. rušení signálu) a po půl vteřině zkusíme znovu
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        client.loop_stop()
        sys.exit(0)
