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

async def main():
    print(f"Startuji NEPRŮSTŘELNÝ skener pro MAC: {TARGET_MAC}...")
    client.publish(TOPIC_STATUS, "SLEEP", retain=True)

    while True:
        try:
            print("Hledám ESP32 (čekám na probuzení)...")
            
            # 1. Hledáme zařízení podle MAC adresy (Timeout 5 vteřin)
            device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=5.0)

            if device:
                # Našli jsme ho! Vypíšeme i sílu signálu pro kontrolu.
                print(f">>> NALEZENO ESP32! Síla signálu (RSSI): {device.rssi} dBm <<<")
                print("Pokouším se o spojení...")
                
                client.publish(TOPIC_STATUS, "CONNECTING", retain=True)

                # Definice callbacku pro odpojení
                def handle_disconnect(_):
                    print("!!! ESP32 ukončilo spojení (Usnulo) !!!")
                    client.publish(TOPIC_STATUS, "SLEEP", retain=True)

                # 2. Připojení přímo k nalezenému zařízení (Nejspolehlivější metoda)
                async with BleakClient(device, timeout=10.0, disconnected_callback=handle_disconnect) as ble_client:
                    
                    print("+++ BLESKOVĚ PŘIPOJENO! Systém je AKTIVNÍ +++")
                    client.publish(TOPIC_STATUS, "READY", retain=True)
                    
                    # Začneme přijímat data z joysticku
                    await ble_client.start_notify(CHAR_UUID, notification_handler)
                    
                    # Držíme spojení, dokud ho ESP32 samo neukončí (15s timeout na ESP)
                    while ble_client.is_connected:
                        await asyncio.sleep(0.5)
            
            else:
                # Zařízení se za 5 vteřin nenašlo (ESP32 spí), smyčka pojede znovu
                pass
                
        except Exception as e:
            # V případě chyby BlueZ modulu vypíšeme varování a chvíli počkáme
            print(f"Chyba při komunikaci: {e}")
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
