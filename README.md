Asistivní Komunikační Hub (Raspberry Pi + ESP32)

Tento repozitář obsahuje zdrojové kódy pro bakalářskou práci zaměřenou na tvorbu asistivního systému pro osoby s omezenou hybností.

Systém se skládá z bezdrátového ovladače (ESP32) pracujícího v režimu Deep Sleep a centrální brány (Raspberry Pi), která zpracovává příkazy přes Bluetooth (BLE) a MQTT.

📂 Struktura repozitáře

ble_bridge.py - Služba pro rychlé a stabilní připojení k ESP32 přes Bluetooth.

web.py - Flask webový server, logika MQTT a uživatelské rozhraní.

templates/index.html - Grafické frontend rozhraní.

setup.sh - Automatický instalační skript pro RPi.

record_ir.sh - Skript pro automatické nahrávání infračervených povelů z TV ovladačů.

🚀 Rychlý start pro Raspberry Pi (Návod pro oživení)

Tento návod předpokládá čistou instalaci Raspberry Pi OS.

1. Stažení repozitáře

Otevřete terminál v Raspberry Pi a stáhněte tento projekt:

git clone <VLOŽTE_ZDE_ODKAZ_NA_VÁŠ_GITHUB_REPOZITÁŘ>
cd <NÁZEV_SLOŽKY_REPOZITÁŘE>


2. Automatická instalace závislostí

Projekt vyžaduje MQTT Broker (Mosquitto), hlasový syntetizér (eSpeak) a Python knihovny. Vše se nainstaluje automaticky:

chmod +x setup.sh
./setup.sh


Následně nainstalujte potřebné Python knihovny:

pip3 install -r requirements.txt --break-system-packages


3. Spuštění systému

Pro běh celého systému potřebujeme spustit dva Python skripty (ideálně ve dvou samostatných oknech terminálu, nebo na pozadí):

Terminál 1 (Bluetooth Brána):
Tento skript bude naslouchat a čekat na probuzení ovladače.

python3 ble_bridge.py


Terminál 2 (Webový server a mozek systému):

python3 web.py


4. Otevření uživatelského rozhraní

Nyní na svém počítači nebo mobilním telefonu (který je na stejné Wi-Fi jako Raspberry Pi) otevřete webový prohlížeč a zadejte IP adresu Raspberry Pi s portem 5000:
http://<IP_ADRESA_RPI>:5000

📺 Integrace InfraČerveného ovládání (TV)

Pokud chcete využívat i ovládání televize, spusťte interaktivní skript, který vás provede nahráním signálů z vašeho stávajícího TV ovladače:

chmod +x record_ir.sh
./record_ir.sh samsung  # Místo samsung zadejte značku vaší TV