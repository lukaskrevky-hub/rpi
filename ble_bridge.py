import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"

CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# OPRAVA 2: MAC adresa je pro Linux neprůstřelná. 
# Zkontroluj, zda sedí tvému ESP32 (použil jsem tu z předchozích zpráv).
TARGET_MAC = "38:18:2B:B3:80:8E"

# --- MQTT Setup ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

def notification_handler(sender, data):
    cmd = data.decode('utf-8')
    print(f"PŘIJATO BLE: {cmd}")
    client.publish(MQTT_TOPIC, cmd)

async def main():
    print(f"Startuji Spolehlivý Hybrid Bridge (Hledám MAC: {TARGET_MAC})...")
    client.publish(TOPIC_STATUS, "READY", retain=True)

    while True:
        try:
            print("Čekám na probuzení joysticku...")
            # Spolehlivé hledání podle MAC adresy. Timeout je nastavený vysoko, 
            # protože malina prostě vyčkává na pozadí, dokud nepohneš páčkou.
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=3600.0)

            if device:
                print("Joystick nalezen! Bleskově se připojuji...")
                async with BleakClient(device) as ble_client:
                    print("Spojení navázáno! Čekám na povely (15s Hybrid režim)...")
                    
                    await ble_client.start_notify(CHAR_UUID, notification_handler)
                    
                    # Držíme smyčku, dokud se ESP32 samo neodpojí a neusne
                    while ble_client.is_connected:
                        await asyncio.sleep(0.1)
                        
                    print("Joystick ukončil spojení a usnul. Jdu znovu skenovat.")
                    
        except Exception as e:
            # V případě drobného zarušení sítě si chvíli počkáme a zkusíme to znovu
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        client.loop_stop()
        sys.exit(0)
