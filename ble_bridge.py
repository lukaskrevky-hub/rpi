import asyncio
from bleak import BleakClient
import paho.mqtt.client as mqtt
import sys

MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"
CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# TVOJE MAC ADRESA ESP32
TARGET_MAC = "10:06:1C:B5:A7:34"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# Událost pro detekci odpojení
disconnect_event = asyncio.Event()

def notification_handler(sender, data):
    cmd = data.decode('utf-8')
    print(f"PŘIJATO BLE: {cmd}")
    client.publish(MQTT_TOPIC, cmd)

def handle_disconnect(client_instance):
    print("!!! ESP32 ukončilo spojení !!!")
    client.publish(TOPIC_STATUS, "SLEEP", retain=True)
    disconnect_event.set()

async def main():
    print(f"Startuji AGRESIVNÍ přímé spojení na MAC: {TARGET_MAC}...")
    client.publish(TOPIC_STATUS, "SLEEP", retain=True)

    while True:
        try:
            # ZDE JE ZMĚNA: Žádný skener! Rovnou dáváme Linuxu příkaz k navázání spojení.
            # Timeout 5.0 znamená, že Linux bude 5 vteřin bušit na dveře a pak to zkusí znovu.
            async with BleakClient(TARGET_MAC, timeout=5.0, disconnected_callback=handle_disconnect) as ble_client:
                
                print("+++ BLESKOVĚ PŘIPOJENO! Systém je AKTIVNÍ +++")
                client.publish(TOPIC_STATUS, "READY", retain=True)
                
                # Začneme přijímat data z joysticku
                await ble_client.start_notify(CHAR_UUID, notification_handler)
                
                # Zastavíme kód a čekáme, dokud nám ESP32 neřekne, že jde spát
                await disconnect_event.wait()
                disconnect_event.clear()
                
        except Exception:
            # Pokud ESP32 zrovna spí, BleakClient po 5 vteřinách vyhodí potichu chybu.
            # My si jen čtvrt vteřiny oddechneme a jdeme na to znovu.
            await asyncio.sleep(0.25)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        client.loop_stop()
        sys.exit(0)
