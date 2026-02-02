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
    print("✅ MQTT OK")
except:
    sys.exit(1)

def notification_handler(sender, data):
    cmd = data.decode('utf-8').strip()
    print(f"--> {cmd}")
    mqtt_client.publish(MQTT_TOPIC, cmd)

def disconnected_callback(client):
    print("⚠️ Odpojeno. Restartuji skener...")

async def main():
    print(f"🚀 Startuji Reaktivní Bridge na {TARGET_MAC}...")
    
    while True:
        # Fáze 1: SKENOVÁNÍ (Čekáme na probuzení)
        # RPi pasivně naslouchá. Dokud ESP32 nezačne vysílat, RPi nic nedělá.
        # Timeout 100s znamená, že čeká dlouho a nezatežuje CPU restartováním skeneru.
        print("📡 Skenuji a čekám na signál...")
        try:
            device = await BleakScanner.find_device_by_address(
                TARGET_MAC, 
                timeout=100.0 
            )
        except Exception:
            device = None
        
        if not device:
            # Timeout vypršel (joystick dlouho spí), zkusíme to znovu
            continue

        # Fáze 2: PŘIPOJENÍ (Okamžitý útok)
        print("⚡ SIGNÁL ZACHYCEN! Okamžitě připojuji...")
        
        try:
            # Použijeme nalezený objekt 'device', to je rychlejší než adresa
            async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=5.0) as client:
                print("✅ PŘIPOJENO!")
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Smyčka udržující spojení naživu
                while client.is_connected:
                    await asyncio.sleep(0.5)
            
            print("ℹ️ Klient ukončen (odpojení).")

        except Exception as e:
            # Pokud se připojení nepovede (např. rušení), zkusíme to hned znovu
            print(f"Chyba připojení: {e}")
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
