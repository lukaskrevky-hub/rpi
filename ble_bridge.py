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

def notification_handler(sender, data):
    try:
        command = data.decode('utf-8').strip()
        print(f"--> Přijato: {command}")
        mqtt_client.publish(MQTT_TOPIC, command)
    except:
        pass

async def main():
    print("Startuji BLE Bridge (Režim přímého připojení)...")
    
    target_address = None

    while True:
        # FÁZE 1: HLEDÁNÍ (Pouze pokud neznáme adresu)
        if target_address is None:
            print("Skenuji okolí a hledám joystick...")
            device = await BleakScanner.find_device_by_filter(
                lambda d, ad: d.name and d.name == ESP_NAME,
                timeout=10.0
            )
            
            if not device:
                print("Joystick nenalezen, zkouším znovu...")
                await asyncio.sleep(1.0)
                continue
                
            target_address = device.address
            print(f"Ukládám adresu joysticku: {target_address}")
        
        # FÁZE 2: PŘÍMÉ PŘIPOJOVÁNÍ (Smyčka pokusů)
        # Tady se točíme, dokud joystick spí. Jakmile se probudí, okamžitě se chytne.
        print(f"Zkouším se připojit k {target_address}...")
        
        try:
            # timeout=3.0 znamená, že zkouší připojení 3 sekundy, pak to zkusí znovu
            async with BleakClient(target_address, timeout=3.0) as client:
                print("PŘIPOJENO! Ovladač je aktivní.")
                
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení živé
                while client.is_connected:
                    await asyncio.sleep(0.1)
                    
                print("Joystick se odpojil (usnul).")
                
        except Exception as e:
            # Joystick asi spí, takže se připojení nepovedlo.
            # Nevadí, zkusíme to hned znovu v dalším cyklu.
            # print(f"Čekám na probuzení... ({e})") 
            await asyncio.sleep(0.2) # Malá pauza, aby procesor nejel na 100%

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
