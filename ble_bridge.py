import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys

MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status"
CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# SPRÁVNÁ MAC ADRESA ESP32
TARGET_MAC = "10:06:1C:B5:A7:34"

# --- MQTT Setup ---
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
    print(f"Startuji obrněný odposlech pro MAC: {TARGET_MAC}...")
    
    # OPRAVA: Na začátku pošleme webu, že systém SPÍ (ne že je připravený!)
    client.publish(TOPIC_STATUS, "SLEEP", retain=True)

    while True:
        try:
            print("Poslouchám vzduch a čekám na záblesk z ESP32...")
            client.publish(TOPIC_STATUS, "SLEEP", retain=True)
            
            # Speciální proměnná (událost), která se sepne, až ESP32 uslyšíme
            found_event = asyncio.Event()
            target_device = None

            # Funkce, která zachytává VŠECHNO, co letí vzduchem
            def detection_callback(device, advertisement_data):
                nonlocal target_device
                # Porovnáváme MAC adresy bez ohledu na velká/malá písmena
                if device.address.lower() == TARGET_MAC.lower():
                    target_device = device
                    found_event.set() # ZASÁH! Zastavujeme hledání

            scanner = BleakScanner(detection_callback)
            await scanner.start()
            
            try:
                # Čekáme donekonečna, dokud se událost nesepne (až pohneš páčkou)
                await found_event.wait()
            finally:
                await scanner.stop()

            if target_device:
                print(">>> ESP32 zachyceno na radaru! Jdu se připojit... <<<")
                client.publish(TOPIC_STATUS, "CONNECTING", retain=True)
                
                # Připojujeme se přímo přes objekt zařízení (100% spolehlivé)
                async with BleakClient(target_device, timeout=10.0) as ble_client:
                    print("+++ ÚSPĚŠNĚ PŘIPOJENO! +++")
                    client.publish(TOPIC_STATUS, "READY", retain=True)
                    
                    await ble_client.start_notify(CHAR_UUID, notification_handler)
                    
                    # Dokud je spojení aktivní, držíme ho
                    while ble_client.is_connected:
                        await asyncio.sleep(0.5)
                        
                    print("--- Ovladač se uspal a odpojil. ---")
            
        except Exception as e:
            print(f"Spojení selhalo nebo spadlo: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        client.publish(TOPIC_STATUS, "SLEEP", retain=True)
        client.loop_stop()
        sys.exit(0)
