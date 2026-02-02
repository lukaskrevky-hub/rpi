import asyncio
from bleak import BleakScanner, BleakClient
import paho.mqtt.client as mqtt
import sys

# ==========================================
# VAŠE MAC ADRESA (Přesná)
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
    print("⚠️ Odpojeno.")

async def main():
    print(f"🚀 Startuji Sniper Mode na {TARGET_MAC}...")
    
    while True:
        try:
            # KROK 1: Čekání na signál (nezkoušíme se připojit naslepo)
            # RPi bude pasivně naslouchat, dokud se joystick neozve.
            # Timeout 60s znamená, že čeká minutu, než restartuje skener (šetří CPU).
            print("📡 Číhám na probuzení joysticku...")
            device = await BleakScanner.find_device_by_address(
                TARGET_MAC, 
                timeout=60.0 
            )
            
            if not device:
                # Timeout vypršel, zkusíme to znovu (čistící cyklus)
                continue

            # KROK 2: Signál zachycen! Okamžitý útok (připojení)
            print("⚡ SIGNÁL ZACHYCEN! Připojuji se...")
            
            # timeout=5.0: Teď už víme, že je vzhůru, takže se musí připojit rychle
            async with BleakClient(device, disconnected_callback=disconnected_callback, timeout=5.0) as client:
                print("✅ PŘIPOJENO!")
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržení spojení
                while client.is_connected:
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            # Pokud se něco pokazí (např. rušení), krátká pauza a znovu do režimu číhání
            print(f"Chyba cyklu: {e}")
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
