import asyncio
from bleak import BleakClient
import paho.mqtt.client as mqtt
import sys

TARGET_MAC = "10:06:1C:B5:A7:36"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

MQTT_BROKER = "localhost"
TOPIC_CMD   = "joystick/command"
TOPIC_STATE = "joystick/status"

mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    mqttc.connect(MQTT_BROKER, 1883, 60)
    mqttc.loop_start()
except Exception as e:
    print("MQTT chyba:", e)
    sys.exit(1)

def publish_state(s):
    print("STAV:", s)
    mqttc.publish(TOPIC_STATE, s, retain=True)

def on_ble_data(_, data):
    mqttc.publish(TOPIC_CMD, data.decode().strip())

def on_disconnect(_):
    publish_state("SLEEP")

async def main():
    publish_state("SLEEP")

    while True:
        try:
            async with BleakClient(
                TARGET_MAC,
                timeout=3.0,
                disconnected_callback=on_disconnect
            ) as client:

                await client.start_notify(UART_TX_CHAR_UUID, on_ble_data)
                publish_state("READY")

                while client.is_connected:
                    await asyncio.sleep(0.5)

        except Exception:
            await asyncio.sleep(0.05)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        publish_state("SLEEP")
        sys.exit(0)
