import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"
CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# TVOJE SPRÁVNÁ MAC ADRESA
TARGET_MAC = "10:06:1C:B5:A7:34"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

def notification_handler(sender, data):
    cmd = data.decode('utf-8').strip()
    print(f"PŘIJATO: {cmd}")
    client.publish(MQTT_TOPIC, cmd)

async def main():
    print("Startuji absolutně neprůstřelný odposlech...")
    client.publish(TOPIC_STATUS, "SLEEP", retain=True)

    while True:
        try:
            print("\n--- Naslouchám surovému signálu ze vzduchu ---")
            
            device_found = None
            found_event = asyncio.Event()

            # Tato funkce se spustí při KAŽDÉM zachyceném signálu z okolí
            def scan_callback(device, advertisement_data):
                nonlocal device_found
                if device.address.lower() == TARGET_MAC.lower():
                    device_found = device
                    found_event.set() # Signál zachycen, zastavujeme čekání!

            # Extrémně rychlý skener, který obchází mezipaměť Linuxu
            scanner = BleakScanner(detection_callback=scan_callback)
            await scanner.start()
            
            # Čekáme na první záblesk z joysticku
            await found_event.wait()
            await scanner.stop()
            
            print(f">>> ZACHYCEN SIGNÁL ({device_found.rssi} dBm)! Okamžitě se připojuji... <<<")
            client.publish(TOPIC_STATUS, "CONNECTING", retain=True)

            def disconnect_callback(c):
                print("--- ESP32 se odpojilo / usnulo ---")
                client.publish(TOPIC_STATUS, "SLEEP", retain=True)

            # Připojujeme se přímo přes nově nalezený objekt, ne přes textovou MAC
            async with BleakClient(device_found, disconnected_callback=disconnect_callback, timeout=10.0) as ble_client:
                print("+++ ÚSPĚŠNĚ PŘIPOJENO +++")
                client.publish(TOPIC_STATUS, "READY", retain=True)
                
                await ble_client.start_notify(CHAR_UUID, notification_handler)
                
                # Zastavíme se zde a čekáme, dokud ESP32 samo neukončí spojení
                while ble_client.is_connected:
                    await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Pokus o spojení selhal: {e}")
            client.publish(TOPIC_STATUS, "SLEEP", retain=True)
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        client.loop_stop()
        sys.exit(0)
