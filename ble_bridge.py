import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"
CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# MAC ADRESA ESP32
TARGET_MAC = "10:06:1C:B5:A7:34"

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
    print(f"Startuji obrněný skener pro MAC: {TARGET_MAC}...")
    client.publish(TOPIC_STATUS, "READY", retain=True)

    while True:
        try:
            print("Hledám joystick v okolí...")
            # Skenujeme 10 vteřin. Pokud nic, smyčka to zkusí znovu.
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=10.0)

            if device:
                print(">>> ESP32 nalezeno! Pokouším se připojit... <<<")
                
                async with BleakClient(device, timeout=10.0) as ble_client:
                    print("+++ ÚSPĚŠNĚ PŘIPOJENO! +++")
                    await ble_client.start_notify(CHAR_UUID, notification_handler)
                    
                    # Dokud je spojení aktivní, malina nedělá nic, jen přijímá příkazy z callbacku
                    while ble_client.is_connected:
                        await asyncio.sleep(0.5)
                        
                    print("--- Ovladač se uspal a odpojil. ---")
            
        except Exception as e:
            # Pokud se např. zaruší signál, vypíšeme chybu a jedeme dál
            print(f"Nepodařilo se připojit: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        client.loop_stop()
        sys.exit(0)
