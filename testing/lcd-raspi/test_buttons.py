import time
import board
import digitalio

# Inisialisasi Tombol (Pull Up)
btn_prev = digitalio.DigitalInOut(board.D17)
btn_prev.direction = digitalio.Direction.INPUT
btn_prev.pull = digitalio.Pull.UP

btn_next = digitalio.DigitalInOut(board.D27)
btn_next.direction = digitalio.Direction.INPUT
btn_next.pull = digitalio.Pull.UP

btn_ok = digitalio.DigitalInOut(board.D22)
btn_ok.direction = digitalio.Direction.INPUT
btn_ok.pull = digitalio.Pull.UP

print("🚀 Program Testing Tombol dimulai.")
print("Tekan tombol untuk melihat outputnya. (Tekan Ctrl+C untuk keluar)")

try:
    # Simpan state sebelumnya agar tidak spam output saat ditekan ditahan
    prev_state_prev = True
    prev_state_next = True
    prev_state_ok = True

    while True:
        # Tombol aktif LOW (False saat ditekan karena pull-up)
        curr_state_prev = btn_prev.value
        curr_state_next = btn_next.value
        curr_state_ok = btn_ok.value

        if not curr_state_prev and prev_state_prev:
            print("✅ Tombol PREV (D17) Ditekan!")
        
        if not curr_state_next and prev_state_next:
            print("✅ Tombol NEXT (D27) Ditekan!")
            
        if not curr_state_ok and prev_state_ok:
            print("✅ Tombol OK (D22) Ditekan!")

        prev_state_prev = curr_state_prev
        prev_state_next = curr_state_next
        prev_state_ok = curr_state_ok
            
        time.sleep(0.05) # Jeda debounce sederhana

except KeyboardInterrupt:
    print("\n🛑 Testing selesai.")
