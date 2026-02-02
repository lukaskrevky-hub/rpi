import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# ==========================================
# ZDE ZADEJTE VAŠI MAC ADRESU ESP32
TARGET_MAC = "38:18:2B:B3:80:8E"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"

# --- MQTT SETUP ---
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
    print("MQTT OK - Bridge připraven")
except:
    sys.exit(1)

def notification_handler(sender, data):
    # Přijímáme data tiše, vypisujeme jen při změně nebo pro debug
    # Pro čistotu konzole zde nevypisujeme každý paket, pokud to není nutné
    try:
        command = data.decode('utf-8').strip()
        # print(f"--> {command}") # Odkomentujte pro debug
        mqtt_client.publish(MQTT_TOPIC, command)
    except:
        pass

def disconnected_callback(client):
    print("Odpojeno (Joystick usnul).")

async def main():
    print(f"Čekám na joystick {TARGET_MAC}...")
    
    while True:
        try:
            # Fáze 1: Čekání na probuzení (Skenování)
            # Používáme timeout 5s pro rychlejší reakci smyčky, 
            # ale skener na pozadí běží a odchytává reklamy
            device = await BleakScanner.find_device_by_address(
                TARGET_MAC, 
                timeout=20.0 
            )
            
            if not device:
                continue

            # Fáze 2: Připojení
            print("Detekován signál -> Připojuji...")
            
            async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=5.0) as client:
                print("PŘIPOJENO! Ovladač aktivní.")
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Smyčka udržující spojení
                while client.is_connected:
                    await asyncio.sleep(1.0)
            
        except Exception:
            # Chyby připojení ignorujeme (joystick asi usnul během procesu), zkusíme znovu
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
