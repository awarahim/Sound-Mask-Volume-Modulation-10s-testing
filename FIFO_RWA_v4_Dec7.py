import pyaudio
import wave
import numpy as np
import time

################################################################################################################################################    
# Generating White Noise, y(n)

# NONBLOCKING MODE (callback)    
def whitenoise(volume):
    
    ##### minimum needed to read a wave #############################
    # open the file for reading.
    wf = wave.open('BrownNoise_60s.wav', 'rb')
    
    def callback_speaker(in_data, frame_count, time_info, status):
        data = wf.readframes(frame_count)
        data = set_volume(data,volume)
        return data, pyaudio.paContinue
    
    #create an audio object
    p2 = pyaudio.PyAudio()
    
    # open stream based on the wave object which has been input
    stream3 = p2.open(format=p2.get_format_from_width(wf.getsampwidth()),
                    channels = wf.getnchannels(),
                    rate = wf.getframerate(),
                    output=True,
                    output_device_index=1,
                    stream_callback=callback_speaker)
    
    
    # start stream
    stream3.start_stream()
    print("speaker playing")
    
    # control how long the stream to play
    time.sleep(60)
        
    # stop stream
        
    stream3.stop_stream()
        
    print('speaker stopped')    
    # cleanup stuff
    stream3.close()
    
    # close PyAudio
    p2.terminate()
    
    wf.close()

def loop_play(stop_event, vol):
    """ Looping 60s whitenoise wav file """
    while not stop_event.wait(0):
        whitenoise(vol)
        
###################################################################################################################################
    
# BLOCKING MODE    
def whitenoise_block(CHUNK=1024, volume):
    ##### minimum needed to read a wave #############################
    # open the file for reading.
    wf = wave.open('BrownNoise_60s.wav')
    
    p2 = pyaudio.PyAudio()
    
    # open stream (2)
    stream3 = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True)

    # read data
    data = wf.readframes(CHUNK)

    # play stream (3)
    while len(data) > 0:
        stream3.write(data)
        data = wf.readframes(CHUNK)
        data = set_volume(data,volume) # could make this part calculate while the stream is playing the audio using threading/multiprocessing
        

    # stop stream (4)
    stream3.stop_stream()
    stream3.close()

    # close PyAudio (5)
    p2.terminate()
    
####################################################################################################################    
def set_volume(datalist,volume):
    """ Change value of list of audio chunks """
    sound_level = (volume / 100.)

    for i in range(len(datalist)):
        chunk = np.fromstring(datalist[i], np.int16)

        chunk = chunk * sound_level

        datalist[i] = chunk.astype(numpy.int16)
        
     return datalist

#####################################################################################################################
def comparator(difference, current_vol, window=10, nu=1, v_threshold=100):
    # nu : the step size of volume being increased or decreased, in percent, ex: 1 = 1%
    # v_threshold : upper limit of the difference between the mics values
    # return: new volume
    # new volume must not be more than 100 and less than 10
    
    #initialize new volume
    new_vol = current_vol
    print("volume difference: ",difference)
    
    # if the difference is within [-100, 100] don't change volume
    if difference >= -v_threshold and difference <= v_threshold:
       new_vol = current_vol
       
       print('same baseline', new_vol)
    
    elif difference < -v_threshold: # reference mic has smaller volume than error mic, lower the volume by nu
        new_vol = current_vol - nu
        print('ref smaller')
    
    elif difference > v_threshold: # reference mic is greater than error mic, then increase the volume by nu
        new_vol = current_vol + nu
        print('error smaller')

    return new_vol

############################################################################################################################
# Third Thread for simultaneous volume modulation
def main_volume_modulation(q3, q4, stop_event, W=10):
 
    time.sleep(3) # wait for moving average to complete calculate and put data into q3 and q4
    
    print('volume modulation started')
    
    current_volume = 10 # initializes current volume
    set_volume(current_volume)
    
    while q3.qsize()> 0 and q4.qsize()> 0 and not stop_event.wait(0.5):
    
        getQ3 = q3.get()
        getQ4 = q4.get()
        
        difference = getQ3 - getQ4    
        new_volume = comparator(difference, current_volume, W, nu=1, v_threshold=100)
        whitenoise(CHUNK=1024, new_volume)
        current_volume = new_volume # set the "current_volume" in modulating_volume function into new_volume because we always get 21, 19, 20
    
    print('volume modulation stopped')
