import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
ESP_NAME = "ESP32-Joystick" # Musí sedět se jménem v ESP32
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

def notification_handler(sender, data):
    try:
        command = data.decode('utf-8').strip()
        print(f"--> Přijato: {command}")
        mqtt_client.publish(MQTT_TOPIC, command)
    except:
        pass

def disconnected_callback(client):
    print("Joystick usnul (odpojeno). Čekám na probuzení...")

async def main():
    print("Startuji Stabilní Bridge (Režim Číhání)...")
    
    target_address = None

    # 1. NAJÍT ADRESU (Jednorázově)
    print("První skenování: Hýbejte joystickem...")
    while target_address is None:
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and d.name == ESP_NAME,
            timeout=5.0
        )
        if device:
            target_address = device.address
            print(f"ZJIŠTĚNA ADRESA: {target_address}")
        else:
            print("... stále hledám ...")

    # 2. SMYČKA ČÍHÁNÍ A PŘIPOJOVÁNÍ
    while True:
        print("Číhám na signál probuzení...")
        
        # Tady RPi jen poslouchá. Nesnaží se připojit, dokud ESP32 nezačne vysílat.
        # To šetří Bluetooth čip před zahlcením chybami.
        device = await BleakScanner.find_device_by_address(
            target_address, 
            timeout=20.0 # Čekáme 20s, pak se smyčka protočí
        )

        if device:
            print(f"Signál zachycen! Připojuji se k {target_address}...")
            
            try:
                async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=5.0) as client:
                    print("PŘIPOJENO! Ovladač je aktivní.")
                    
                    await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                    
                    # Smyčka udržující spojení
                    while client.is_connected:
                        await asyncio.sleep(1.0)
                        
            except Exception as e:
                print(f"Chyba připojení (asi usnul příliš rychle): {e}")
                await asyncio.sleep(0.5)
        else:
            # Timeout vypršel, joystick asi spí. Zkusíme číhat znovu.
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
