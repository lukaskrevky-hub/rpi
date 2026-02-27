import asyncio
from bleak import BleakClient, BleakScanner
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

def notification_handler(sender, data):
    cmd = data.decode('utf-8')
    print(f"PŘIJATO BLE: {cmd}")
    client.publish(MQTT_TOPIC, cmd)

async def connect_and_listen():
    print("Hledám ESP32 (ignoruji starou paměť, čekám na čerstvý signál)...")
    
    # TRIK 1: Použijeme filtr. To donutí Linux ignorovat starou paměť
    # a musí fyzicky uslyšet nový inzertní paket z ESP32.
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: d.address.lower() == TARGET_MAC.lower(),
        timeout=5.0
    )

    if not device:
        return # Nic jsme neslyšeli, smyčka v main() se zopakuje

    print(f">>> ZACHYCEN ČERSTVÝ SIGNÁL! (RSSI: {device.rssi} dBm) <<<")
    client.publish(TOPIC_STATUS, "CONNECTING", retain=True)

    disconnect_event = asyncio.Event()

    def handle_disconnect(_):
        print("!!! ESP32 ukončilo spojení (Usnulo) !!!")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        disconnect_event.set()

    try:
        # TRIK 2: Předáme BleakClientovi přímo textovou adresu, ne objekt 'device'. 
        # Na Raspberry Pi to obchází velmi nepříjemný bug v BlueZ modulu.
        async with BleakClient(TARGET_MAC, disconnected_callback=handle_disconnect, timeout=10.0) as ble_client:
            print("+++ BLESKOVĚ PŘIPOJENO! Systém je AKTIVNÍ +++")
            client.publish(TOPIC_STATUS, "READY", retain=True)
            
            await ble_client.start_notify(CHAR_UUID, notification_handler)
            
            # Čekáme, dokud se událost nesepne (ESP32 se neodpojí)
            await disconnect_event.wait()
            
    except Exception as e:
        print(f"Chyba při pokusu o spojení: {e}")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        await asyncio.sleep(1)

async def main():
    print(f"Startuji FINÁLNÍ a NEJSTABILNĚJŠÍ verzi pro MAC: {TARGET_MAC}")
    client.publish(TOPIC_STATUS, "SLEEP", retain=True)

    while True:
        await connect_and_listen()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        client.loop_stop()
        sys.exit(0)
