import pexpect
import sys

def run_ssh():
    print("Membuka koneksi SSH ke 'vtol' untuk setup Samba...")
    child = pexpect.spawn('ssh -o StrictHostKeyChecking=no vtol', encoding='utf-8')
    child.logfile = sys.stdout
    
    i = child.expect(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=15)
    if i == 0:
        child.sendline('pi')
        child.expect(r'pi@raspberrypi', timeout=10)
        
        print("\n--- Menginstall Samba ---")
        child.sendline('sudo apt-get update')
        child.expect(r'pi@raspberrypi', timeout=60)
        
        child.sendline('sudo apt-get install -y samba samba-common-bin')
        child.expect(r'pi@raspberrypi', timeout=180)
        
        print("\n--- Konfigurasi Folder Samba ---")
        child.sendline('sudo cp /etc/samba/smb.conf /etc/samba/smb.conf.backup')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        smb_config = """
[PiShare]
   path = /home/pi
   browseable = yes
   writeable = yes
   create mask = 0777
   directory mask = 0777
   public = no
   valid users = pi
"""
        for line in smb_config.strip().split('\n'):
            child.sendline(f"echo '{line}' | sudo tee -a /etc/samba/smb.conf")
            child.expect(r'pi@raspberrypi', timeout=2)
            
        print("\n--- Membuat Password Samba untuk User 'pi' ---")
        child.sendline('(echo "pi"; echo "pi") | sudo smbpasswd -s -a pi')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        print("\n--- Restart Service Samba ---")
        child.sendline('sudo systemctl restart smbd')
        child.expect(r'pi@raspberrypi', timeout=10)
        
        print("\n--- Mengecek Status Samba ---")
        child.sendline('sudo systemctl status smbd --no-pager | grep Active')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('exit')
        child.expect(pexpect.EOF)
    else:
        print("Gagal masuk SSH. Cek koneksi cloudflared kamu.")

if __name__ == '__main__':
    run_ssh()
