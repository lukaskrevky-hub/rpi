import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
TARGET_MAC = "10:06:1C:B5:A7:34"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"

# --- MQTT SETUP ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print(f"MQTT připojeno na {MQTT_BROKER}")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

def publish_status(status):
    """Odesílá stav (READY/SLEEP/CONNECTING) na web."""
    print(f"STAV -> {status}")
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    """Zpracuje příkaz přijatý přes Bluetooth a pošle ho do MQTT."""
    try:
        command = data.decode('utf-8').strip()
        print(f"Přijato: {command}")
        client.publish(MQTT_TOPIC, command)
    except Exception as e:
        print(f"Chyba při dekódování: {e}")

async def main():
    print(f"Startuji most pro joystick {TARGET_MAC}...")
    publish_status("SLEEP")

    while True:
        try:
            print("\nNaslouchám a čekám na probuzení joysticku...")
            
            # Hledáme zařízení aktivně v okolí (vyhne se to zombie spojení v Linuxu)
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=10.0)

            if device:
                print(f">>> Joystick nalezen ({device.rssi} dBm)! Připojuji se...")
                publish_status("CONNECTING")

                def disconnected_callback(client):
                    print("Joystick se odpojil (usnul).")
                    publish_status("SLEEP")

                async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=10.0) as ble_client:
                    print("+++ SPOJENO! Ovladač je aktivní +++")
                    publish_status("READY")
                    
                    await ble_client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    # Držíme spojení, dokud je ESP32 online
                    while ble_client.is_connected:
                        await asyncio.sleep(0.5)
            
        except Exception as e:
            # Tichá chyba (zařízení nenalezeno), zkusíme to v dalším cyklu
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji most...")
        publish_status("SLEEP")
        sys.exit(0)
