import pexpect
import sys

def run_ssh():
    print("Starting SSH...")
    child = pexpect.spawn('ssh -o StrictHostKeyChecking=no pi@192.168.6.200', encoding='utf-8')
    child.logfile = sys.stdout
    
    i = child.expect(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=10)
    if i == 0:
        # User file says 'ppi', but user prompt said 'pi'. I'll try 'ppi' first, if fails, 'pi'
        child.sendline('ppi')
        
        # Check if we get the prompt or another password prompt
        i2 = child.expect([r'pi@raspberrypi', 'password:', pexpect.TIMEOUT], timeout=5)
        if i2 == 1: # Password failed, try 'pi'
            child.sendline('pi')
            child.expect([r'pi@raspberrypi', pexpect.TIMEOUT], timeout=5)
            
        print("\n--- Logged in successfully ---")
        
        # Add profile manually
        child.sendline('sudo nmcli con add type wifi ifname wlan0 con-name esp ssid esp')
        i3 = child.expect([r'password for pi:', r'pi@raspberrypi', pexpect.TIMEOUT], timeout=5)
        if i3 == 0:
            child.sendline('ppi') # Assuming sudo password is same
            child.expect([r'pi@raspberrypi', 'Sorry, try again'], timeout=5)
            # If wrong, pexpect will just continue to the next prompt, it's fine for a quick script
        
        child.sendline('sudo nmcli con modify esp wifi-sec.key-mgmt wpa-psk wifi-sec.psk 12341234')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('sudo nmcli con up esp')
        child.expect(r'pi@raspberrypi', timeout=15)
        
        child.sendline('ip a show wlan0')
        child.expect(r'pi@raspberrypi', timeout=5)
        
        child.sendline('exit')
        child.expect(pexpect.EOF)
    else:
        print("Failed to get SSH password prompt.")

if __name__ == '__main__':
    run_ssh()
