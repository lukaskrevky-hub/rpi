import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
# Musí odpovídat kódům v ESP32!
ESP_NAME = "ESP32-Joystick"
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# MQTT Konfigurace
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"

# --- MQTT SETUP ---
mqtt_client = mqtt.Client()
try:
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start() # Běží na pozadí
    print(f"MQTT připojeno k {MQTT_BROKER}")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- CALLBACK FUNKCE ---
# Toto se spustí, když ESP32 pošle data
def notification_handler(sender, data):
    try:
        command = data.decode('utf-8').strip()
        print(f"--> Přijato z BLE: {command}")
        
        # Přeposlání do MQTT
        mqtt_client.publish(MQTT_TOPIC, command)
        print(f"<-- Odesláno do MQTT: {command}")
    except Exception as e:
        print(f"Chyba při zpracování dat: {e}")

# --- HLAVNÍ SMYČKA ---
async def main():
    print("Startuji BLE Bridge...")
    
    while True:
        print("Skenuji a hledám ESP32-Joystick...")
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and d.name == ESP_NAME
        )

        if not device:
            # Pokud nenajde (ESP spí), počká chvíli a zkusí znovu
            await asyncio.sleep(2.0)
            continue

        print(f"Nalezeno: {device.name} ({device.address}) - Připojuji...")
        
        try:
            async with BleakClient(device) as client:
                print("Připojeno! Čekám na data...")
                
                # Přihlášení k odběru notifikací
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Smyčka, která udržuje spojení živé, dokud se ESP neodpojí
                while client.is_connected:
                    await asyncio.sleep(1.0)
                    
                print("Zařízení se odpojilo (asi šlo spát).")
                
        except Exception as e:
            print(f"Chyba spojení: {e}")
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")

        mqtt_client.loop_stop()

