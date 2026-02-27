import asyncio
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt
import sys
import subprocess

# ==========================================
# CÍLOVÁ MAC ADRESA PRO BLUETOOTH
# (Bluetooth MAC je u ESP32 vždy o +2 vyšší než Wi-Fi MAC. Wi-Fi byla 34, takže BLE je 36)
TARGET_MAC = "10:06:1C:B5:A7:36"
# ==========================================

UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "joystick/command"
TOPIC_STATUS = "joystick/status" 

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    print("MQTT připojeno.")
except Exception as e:
    print(f"Chyba MQTT: {e}")
    sys.exit(1)

def publish_status(status):
    print(f"STAV -> {status}") 
    client.publish(TOPIC_STATUS, status, retain=True)

def notification_handler(sender, data):
    command = data.decode('utf-8').strip()
    print(f"Přijato z BLE: {command}")
    client.publish(MQTT_TOPIC, command)

def disconnected_callback(client):
    print(">>> Ztráta spojení (Joystick usnul nebo je mimo dosah).")
    publish_status("SLEEP")

async def connect_and_listen():
    print(f"--- SPUŠTĚNO SKENOVÁNÍ A PŘIPOJOVÁNÍ NA {TARGET_MAC} ---")
    publish_status("SLEEP")
    
    while True:
        try:
            print("\nSkener: Prohledávám okolí (4 vteřiny)...")
            
            # Od verze knihovny Bleak 0.19+ se musí pro RSSI použít return_adv=True
            devices_dict = await BleakScanner.discover(timeout=4.0, return_adv=True)
            target_device = None
            target_rssi = None
            
            # Najdeme náš ovladač (buď podle jména nebo podle MAC)
            for address, (d, adv) in devices_dict.items():
                if d.address.lower() == TARGET_MAC.lower() or (d.name and "ESP-JOY" in d.name):
                    target_device = d
                    target_rssi = adv.rssi
                    break
            
            if not target_device:
                print("Zařízení nenalezeno, zkouším to znovu...")
                await asyncio.sleep(1.0)
                continue
                
            print(f"\n>>> NALEZENO NÁŠ OVLADAČ! (Jméno: {target_device.name}, MAC: {target_device.address}, RSSI: {target_rssi} dBm) <<<")
            publish_status("CONNECTING") 
            
            # WORKAROUND PRO RASPBERRY PI ("In Progress" bug):
            # Musíme dát Bluetooth modulu chvíli oddech po skenování, než navážeme spojení.
            print("Dávám modulu vteřinu na oddech před spojením...")
            await asyncio.sleep(1.0)
            
            async with BleakClient(target_device, disconnected_callback=disconnected_callback, timeout=3.0) as client_ble:
                print("+++ PŘIPOJENO! Ovladač je aktivní. +++")
                publish_status("READY") 
                
                # Zapneme příjem zpráv z joysticku
                await client_ble.start_notify(UART_TX_CHAR_UUID, notification_handler)
                
                # Udržujeme spojení dokud se ovladač po 15 vteřinách nečinnosti sám neuspí
                while client_ble.is_connected:
                    await asyncio.sleep(0.5)
            
        except Exception as e:
            error_msg = str(e)
            print(f"Chyba při komunikaci: {error_msg}")
            
            # Pokud se BlueZ zasekne, provedeme tvrdý restart konkrétního spojení v Linuxu
            if "In Progress" in error_msg or "br-connection-canceled" in error_msg:
                print("!!! Zjištěno zaseknutí (In Progress). Provádím tvrdý úklid...")
                subprocess.run(["bluetoothctl", "disconnect", TARGET_MAC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await asyncio.sleep(2.0)
            else:
                await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(connect_and_listen())
    except KeyboardInterrupt:
        print("\nUkončuji program...")
        publish_status("SLEEP")
        sys.exit(0)


