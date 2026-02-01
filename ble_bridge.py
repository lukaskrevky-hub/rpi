import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# --- KONFIGURACE ---
# Musí odpovídat jménu v ESP32!
ESP_NAME = "ESP32-Joystick"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# --- MQTT SETUP ---
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"

# Oprava pro novější verze knihovny (odstranění warningu)
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.loop_start()
    print(f"MQTT připojeno k {MQTT_BROKER}")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

# --- CALLBACK FUNKCE ---
def notification_handler(sender, data):
    try:
        command = data.decode('utf-8').strip()
        print(f"--> Přijato z BLE: {command}")
        mqtt_client.publish(MQTT_TOPIC, command)
        # print(f"<-- Odesláno do MQTT: {command}") # Zakomentováno pro čistší log
    except Exception as e:
        print(f"Chyba při zpracování: {e}")

# --- HLAVNÍ SMYČKA ---
async def main():
    print("Startuji Stabilní BLE Bridge (Optimalizováno)...")
    
    while True:
        print("Skenuji...")
        
        # OPTIMALIZACE 1: Timeout 5s neznamená, že čeká 5s.
        # Znamená to "hledej AŽ 5 sekund". Jakmile ho najde (třeba za 0.2s), okamžitě pokračuje dál.
        # Krátké timeouty (např. 1s) způsobují, že se skener pořád restartuje, což zdržuje.
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and d.name == ESP_NAME,
            timeout=5.0
        )

        if not device:
            # Pokud nenajde, nečekáme a jdeme ihned skenovat znovu
            continue

        print(f"Nalezeno: {device.name} - Připojuji...")
        
        try:
            async with BleakClient(device) as client:
                print("PŘIPOJENO! Ovladač je aktivní.")
                
                # Aktivace notifikací
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Smyčka udržující spojení
                while client.is_connected:
                    # OPTIMALIZACE 2: Kontrolujeme stav častěji (0.1s),
                    # abychom rychle zjistili odpojení a mohli začít hned hledat.
                    await asyncio.sleep(0.1)
                    
                print("Zařízení se odpojilo (asi šlo spát).")
                
        except Exception as e:
            # Pokud se připojení nepovede (např. joystick usnul těsně před připojením)
            print(f"Chyba spojení: {e}")
            # Malá pauza, aby se Bluetooth nezahltilo, pokud je joystick vypnutý
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
