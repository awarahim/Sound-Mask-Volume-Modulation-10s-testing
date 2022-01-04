import pyaudio

p = pyaudio.PyAudio()
devices = []

for ii in range(p.get_device_count()):
    devices.append(p.get_device_info_by_index(ii).get('name'))
    print(p.get_device_info_by_index(ii).get('name'))
