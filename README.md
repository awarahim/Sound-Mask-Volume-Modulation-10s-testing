# Sound-Mask-Volume-Modulation
What this code does:
Checking the difference in signal of reference and error mic and modulate the volume such that the signal of reference and error becomes the same.
Volume is changed by calling alsa system mixer and changed the volume by 1%.


What you need:
1. 2 USB microphones
2. 1 set of speaker with 3.5mm audio jack
3. Raspberry Pi 4B+

Dependencies: 
1) Installing Pyaudio in Raspi 4 and Python3: 
      - in terminal write: sudo apt install python3-pyaudio



Successed in looping the sound. refered: https://stackoverflow.com/questions/47513950/how-to-loop-play-an-audio-with-pyaudio (first solution)

01/12/2022
Problem: Volume changing does not happen. System volume changed but not the output of the speaker
reference: https://raspberrypi.stackexchange.com/questions/112954/how-to-restore-audio-output-after-updating-raspbian-buster-on-pi4
this might due to update of the raspberry pi
> sudo nano /etc/pulse/default.pa
edited the line : "set-default-sink output" to "set-default-sink 1"
result: did nothing

Probably I need to search for "how to control volume with pyaudio"
https://stackoverflow.com/questions/25868428/pyaudio-how-to-check-volume

1/20/2022 UPDATE
Updated the code to multiply the data bytes of audio file with fraction of volume. See set_volume() function. 
