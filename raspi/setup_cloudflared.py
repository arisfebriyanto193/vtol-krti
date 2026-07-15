import pexpect
import sys

def run_ssh():
    print("Membuka koneksi SSH ke Raspberry Pi di 192.168.6.247...")
    child = pexpect.spawn('ssh -o StrictHostKeyChecking=no pi@192.168.6.247', encoding='utf-8')
    child.logfile = sys.stdout
    
    i = child.expect(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=10)
    if i == 0:
        child.sendline('pi')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        print("\n--- Mengecek Koneksi Internet ---")
        child.sendline('curl -s -I https://github.com | head -n 1')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        if '200' not in child.before and '301' not in child.before and '302' not in child.before:
            print("\n⚠️ PERINGATAN: Raspberry Pi sepertinya masih terblokir Captive Portal atau tidak ada internet.")
            print("Saya akan tetap mencoba menginstall, tapi kemungkinan akan gagal didownload.")
            
        print("\n--- Menginstall Cloudflared (Binary Version) ---")
        # Menggunakan versi aarch64 (arm64) karena OS-nya 64-bit
        child.sendline('wget -q --show-progress https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -O cloudflared')
        # Download bisa memakan waktu, timeout diperpanjang
        child.expect(r'pi@raspberrypi', timeout=60)
        
        child.sendline('sudo mv cloudflared /usr/local/bin/cloudflared')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('sudo chmod +x /usr/local/bin/cloudflared')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        print("\n--- Cek Versi Cloudflared ---")
        child.sendline('cloudflared --version')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('exit')
        child.expect(pexpect.EOF)
    else:
        print("Gagal masuk SSH. Pastikan IP 192.168.6.247 benar dan Raspberry Pi aktif.")

if __name__ == '__main__':
    run_ssh()
