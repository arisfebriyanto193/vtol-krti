import pexpect
import base64
import sys

script_content = """#!/bin/bash
if [ "$#" -ne 2 ]; then
    echo "Penggunaan: ./ganti_wifi.sh <SSID> <PASSWORD>"
    exit 1
fi
SSID=$1
PASSWORD=$2

echo "==================================="
echo "Menghubungkan ke WiFi: $SSID"
echo "==================================="

# Hapus koneksi lama jika ada
sudo nmcli con delete "$SSID" 2>/dev/null

# Buat profil dan konfigurasi password
sudo nmcli con add type wifi ifname wlan0 con-name "$SSID" ssid "$SSID"
sudo nmcli con modify "$SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASSWORD"

# Mulai koneksi
sudo nmcli con up "$SSID"

if [ $? -eq 0 ]; then
    echo -e "\n✅ Berhasil terkoneksi ke $SSID!"
    echo "IP Address kamu saat ini:"
    ip -4 a show wlan0 | grep inet
else
    echo -e "\n❌ Gagal terkoneksi ke $SSID! Cek kembali password."
fi
"""

b64 = base64.b64encode(script_content.encode()).decode()

def run_ssh():
    print("Membuka koneksi SSH ke Raspberry Pi...")
    child = pexpect.spawn('ssh -o StrictHostKeyChecking=no pi@192.168.6.200', encoding='utf-8')
    child.logfile = sys.stdout
    
    i = child.expect(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=10)
    if i == 0:
        child.sendline('pi')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        print("\nMembuat file script ganti_wifi.sh...")
        cmd = f"echo '{b64}' | base64 -d > /home/pi/ganti_wifi.sh"
        child.sendline(cmd)
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('chmod +x /home/pi/ganti_wifi.sh')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('ls -l /home/pi/ganti_wifi.sh')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('exit')
        child.expect(pexpect.EOF)
    else:
        print("Gagal masuk SSH.")

if __name__ == '__main__':
    run_ssh()
