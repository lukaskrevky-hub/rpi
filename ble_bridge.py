import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
ESP_NAME = "ESP32-Joystick"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# --- MQTT SETUP ---
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
    print(f"MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# Globální proměnné pro řízení stavu
found_device = None
stop_event = asyncio.Event()

def notification_handler(sender, data):
    try:
        command = data.decode('utf-8').strip()
        print(f"--> Přijato: {command}")
        mqtt_client.publish(MQTT_TOPIC, command)
    except:
        pass

# Tato funkce se spustí OKAMŽITĚ, jakmile RPi zachytí signál
def detection_callback(device, advertisement_data):
    global found_device
    # Hledáme podle jména
    if device.name == ESP_NAME:
        print(f"SIGNÁL ZACHYCEN: {device.name} ({device.address})")
        found_device = device
        stop_event.set() # Okamžitě ukončí skenování a jde se připojovat

async def main():
    global found_device
    print("Startuji Rychlý BLE Bridge...")

    while True:
        found_device = None
        stop_event.clear()
        
        print("📡 Čekám na probuzení joysticku...")
        
        # Spustíme skener na pozadí s callbackem
        scanner = BleakScanner(detection_callback=detection_callback)
        await scanner.start()
        
        # Čekáme, dokud callback neřekne "MÁM HO!"
        # Tím odpadá zbytečné čekání na timeout
        await stop_event.wait()
        
        # Jakmile ho máme, zastavíme skener a jdeme se připojit
        await scanner.stop()
        
        if found_device:
            print(f"Připojuji se k {found_device.address}...")
            try:
                async with BleakClient(found_device) as client:
                    print("PŘIPOJENO! Ovladač je aktivní.")
                    await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    # Smyčka udržující spojení
                    while client.is_connected:
                        await asyncio.sleep(0.1)
                        
                    print("Joystick se odpojil (usnul).")
            except Exception as e:
                print(f"Chyba připojení: {e}")
                # Krátká pauza před dalším pokusem, aby se Bluetooth nezahltilo
                await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
