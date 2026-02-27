import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys
import subprocess

MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"
CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# SPRÁVNÁ MAC ADRESA
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
    print("\nHledám ESP32 (Pohněte páčkou pro probuzení)...")
    
    # Rychlé a spolehlivé hledání (timeout 5s)
    device = await BleakScanner.find_device_by_address(TARGET_MAC, timeout=5.0)

    if not device:
        return # Nic jsme neslyšeli, zkusíme to hned znovu

    print(f">>> ESP32 NALEZENO! (Síla signálu: {device.rssi} dBm) <<<")
    client.publish(TOPIC_STATUS, "CONNECTING", retain=True)

    disconnect_event = asyncio.Event()

    def handle_disconnect(_):
        print("!!! ESP32 ukončilo spojení (Usnulo) !!!")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        disconnect_event.set()

    try:
        # Připojujeme se přímo přes nalezený OBJEKT, nikoliv přes MAC adresu
        # To nutí Linux vynechat cache a připojit se okamžitě
        async with BleakClient(device, disconnected_callback=handle_disconnect, timeout=10.0) as ble_client:
            print("+++ BLESKOVĚ PŘIPOJENO! Systém je AKTIVNÍ +++")
            client.publish(TOPIC_STATUS, "READY", retain=True)
            
            await ble_client.start_notify(CHAR_UUID, notification_handler)
            
            # Čekáme na slušné odpojení z ESP32 po 15 vteřinách
            await disconnect_event.wait()
            
    except Exception as e:
        print(f"Chyba při pokusu o spojení: {e}")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        
        # Pojistka pročištění případně zaseklé paměti Bluetooth
        subprocess.run(["bluetoothctl", "remove", TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(1)

async def main():
    print(f"Startuji ULTRA-RYCHLOU verzi pro MAC: {TARGET_MAC}")
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
