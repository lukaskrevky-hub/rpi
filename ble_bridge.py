import asyncio
from bleak import BleakClient, BleakError
import paho.mqtt.client as mqtt
import sys

# ==========================================
# VAŠE MAC ADRESA
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
    print("⚠️ Odpojeno. Okamžitý restart...")

async def main():
    print(f"🚀 Startuji Agresivní Direct Connect na {TARGET_MAC}...")
    print("TIP: Pokud to nefunguje, restartujte Bluetooth: 'sudo systemctl restart bluetooth'")
    
    while True:
        try:
            print("🔗 Pokus o připojení...")
            
            # timeout=20.0: RPi bude 20 sekund viset na lince a čekat, až se ESP ozve.
            # Jakmile ESP pípne, spojení se naváže OKAMŽITĚ (bez skenování).
            async with BleakClient(TARGET_MAC, disconnected_callback=disconnected_callback, timeout=20.0) as client:
                print("✅ PŘIPOJENO! Ovladač je aktivní.")
                
                # Zapnutí notifikací
                await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Smyčka udržující spojení
                while client.is_connected:
                    await asyncio.sleep(0.1)
                    
        except BleakError as e:
            # "Device not found" nebo "Not connected" - to je normální, když ESP spí.
            # print(".", end="", flush=True)
            # Okamžitě zkusíme znovu - žádné dlouhé čekání!
            await asyncio.sleep(0.1)
            
        except Exception as e:
            print(f"Chyba: {e}")
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ukončuji...")
        mqtt_client.loop_stop()
