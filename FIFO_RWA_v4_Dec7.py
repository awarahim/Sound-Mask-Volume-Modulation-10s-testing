#!/usr/bin/python3
# -*- coding:utf-8 -*-

import pyaudio
import wave

import signal
import sys

import multiprocessing as mp
import threading

import numpy as np
import time
from subprocess import call

# Constants for audio devices
FORMAT  = pyaudio.paInt16    # 24-bit the mic is 24-bit with sample rate of 96kHz
CHANNELS = 2                 # number of audio streams to use. Since there is one speaker and one mic, use 2 streams
RATE = 48000                # 48kHz since mic is specific at 48kHz
FRAMES_PER_BUFFER = 1024    # 

# calculate RMS of data chunk
def rms(data):
    if len(data) == 1: return print('data length =1')
    fromType = np.int16
    d = np.frombuffer(data,fromType).astype(np.float) # convert data from buffer from int16 to float to calculate rms
    rms = np.sqrt(np.mean(d**2))
    return int(rms)

def ref_mic(p, q1, duration):   
    
    def callback(in_data, frame_count, time_info, status):
            data = rms(in_data)
            q1.put(data)
#             print("q1:", q1.get())
            return in_data, pyaudio.paContinue
        
    stream2 = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        frames_per_buffer=FRAMES_PER_BUFFER,
        input=True,
        input_device_index=2,
        stream_callback = callback)
    
    # start stream
    stream2.start_stream()
    
    # control how long the stream to record
    time.sleep(duration)
    
    # stop stream
    stream2.stop_stream()
    
    stream2.close()
    p.terminate()
    
    # Send signal it stopped recording
    q1.put("Stop")
    
def error_mic(p, q2, duration):
    def callback2(in_data2, frame_count2, time_info2, status2):
            data2 = rms(in_data2)
            q2.put(data2)
#             print("q2:", q2.get())
            return in_data2, pyaudio.paContinue
        
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        frames_per_buffer=FRAMES_PER_BUFFER,
        input=True,
        input_device_index=3,
        stream_callback = callback2)
    
    # start stream
    stream.start_stream()
    
    # duration control how long the stream to record
    time.sleep(duration)
    
    # stop stream
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    q2.put("Stop")


def Multithread_mic(q1, q2, duration):
    p = pyaudio.PyAudio()
    t1 = threading.Thread(target=ref_mic, args=(p,q1,duration))
    t2 = threading.Thread(target=error_mic, args=(p,q2, duration))
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    print("Mic recording is stopped")
#######################################################################################################################################    
# Second Thread for simultaneous calculate the moving average of compiled RMS values
def Moving_Average(q1, q2, q3, q4, window= 10):
    
    ref = []
    err = []    
    
    time.sleep(1) # allow the q's fill up apparently until 7 data points only after 1s, so I put 2s to get more data 
    print("size: ", q1.qsize(), q2.qsize()) 
    while q1.qsize()> 0 and q2.qsize()> 0:  #check if the qs are not empty
        
        print('Moving Average Started')
        
        # Put first Window-1 to be the same number as non-averaged rms number
        for n in range(0,window):
                ref.append(q1.get())
                err.append(q2.get())
                q3.put(ref[n])
                q4.put(err[n])
#                 print(q1.qsize(),q2.qsize())
                
        #Calculate the mean of first (window)
        Mprev_ref = np.mean(ref)
        Mprev_err = np.mean(err)
        
        # Put the means at the window'th position
        q3.put(Mprev_ref)
        q4.put(Mprev_err)
        
        #empty ref and err
        ref = []
        err = []
        
        print('Done first window')
#         print(q1.qsize(), q2.qsize())
        
        
        while True:
#             print(q1.qsize(),q2.qsize())
            
            getQ1 = q1.get()
            getQ2 = q2.get()
            
            if getQ1 == "Stop" or getQ2 == "Stop":
                break

            # Calculate next one step window of the data
            Mnew_ref = Mprev_ref + (getQ1 - Mprev_ref)/window
            Mnew_err = Mprev_err + (getQ2 - Mprev_err)/window
#             print(Mnew_ref, Mnew_err)
        
            # New mean becomes the previous mean
            Mprev_ref = Mnew_ref
            Mprev_err = Mnew_err
            
            # Save the data in the respective queues
            q3.put(Mprev_ref)
            q4.put(Mprev_err)
        
        print('Im out')
        # Stopping signal for volume modulation thread
        q3.put("Stop")
        q4.put("Stop")
        break    
    print('Moving Average Stopped')
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
       
#        print('same baseline')
    
    elif difference < -v_threshold: # reference mic has smaller volume than error mic, lower the volume by nu
        new_vol = current_vol - nu
#         print('ref smaller')
    
    elif difference > v_threshold: # reference mic is greater than error mic, then increase the volume by nu
        new_vol = current_vol + nu
#         print('error smaller')

    return new_vol

# Getting Raspi's current speaker volume
def set_volume(volume=20):
    # Set the current volume to a percentage. default is 20%
        
    if volume > 0 and volume <= 70: # 70 might be the loudest and still not disturbing. Need to check!
        call(["amixer", "-D", "pulse", "sset", "Master", str(volume)+"%"])
    
    else:
        volume = 0 # temporary conditions

# Third Thread for simultaneous volume modulation
def main_volume_modulation(q3, q4, W=10):
    # Need to stop modulation when mic stopped running!
    time.sleep(1) # wait for moving average to start
    
    print('volume modulation started')
    
#     start = time.time()
    RATE = 48000             # 48kHz
    FRAMES_PER_BUFFER = 1024
    set_volume(10)
    current_volume = 0 # initializes current volume
    
    while True:
    
        getQ3 = q3.get()
        getQ4 = q4.get()
        print("vol_mod:",getQ3, getQ4)
        
        if getQ3 == "Stop" and getQ4 == "Stop":
                break
        difference = getQ3 - getQ4    
        new_volume = comparator(difference, current_volume, W)
        set_volume(new_volume)
        current_volume = new_volume # set the "current_volume" in modulating_volume function into new_volume because we always get 21, 19, 20
    
    print('volume modulation stopped')
    
################################################################################################################################################    
# Generating White Noise, y(n)
    
def whitenoise(duration=4):
    
    ##### minimum needed to read a wave #############################
    # open the file for reading.
    wf = wave.open('BrownNoise_60s.wav', 'rb')
    
    def callback_speaker(in_data, frame_count, time_info, status):
        data = wf.readframes(frame_count)
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
    time.sleep(duration)
    
    # stop stream
    stream3.stop_stream()

        
    print('speaker stopped')    
    # cleanup stuff
    stream3.close()
    wf.close()
    # close PyAudio
    p2.terminate()
    


############################# Main code ###################################################
def thread_mask():    
    
    print('Start')
    period = 10
    window = 10
    q1 = mp.Queue()
    q2 = mp.Queue()
    q3 = mp.Queue()
    q4 = mp.Queue()

    p1 = mp.Process(target=Multithread_mic, args=(q1,q2,period))
    p2 = mp.Process(target=whitenoise, args=(period,))
    p3 = mp.Process(target=Moving_Average, args=(q1, q2, q3, q4, window))
    p4 = mp.Process(target=main_volume_modulation, args = (q3,q4, window))
    
    p1.start()
    p2.start()
    p3.start()
    p4.start()
    
    p1.join()
    p2.join()
    p3.join()
    p4.join()
            
    print('End')

#######################################################################################################
   
if __name__ == '__main__':
    
    thread_mask()
    
####################### Notes ##########################################
# as of 10/19/2021:
#    - the rate of changing is quite fast,
#    - what of the difference between ref and err is still large,
#      forcing the new_vol calculated by the comparator() becomes negative? the possibility of volume becomes 100% is BAD!
#    - need to add the function for the speaker as well
#    - figure out the upper limit for speaker volume (70/60?)
#    - do test with speaker

# 10/20/2021:
# - need to make sure the modulation code is correct
# - Make sure the volume modulation stopped when mic is stopped collecting
# - google real-time moving average

# 10/21/2021:
# - margin in difference of comparator (v_threshold) depends on the window size
# - how to control the above?
# - noticed that the changes is still there although the mics are in the same region
# - need to add another thread for playing the whitenoise
# - test the mic at different locations
# - need to control the timing of each thread since they need to syncronise reasonably. When/how to stop the loop?

# 10/26/2021
# - with all threads as multithreading, there's error: Backend terminated or disconnected. Use 'Stop/Restart' to restart.

# 10/28/2021
# - Typo = Mnew_err = Mprev_err + (q1.get() - Mprev_err)/window should be q2.get()
# - without whitenoise thread, run entire code,
# - Mean of the first window only finished after the volume modulation is finished.
# - Need to do multiprocessing for computational heavy tasks
# - not yet changed from multithreading to multiprocessing
# - Mic stopped first, then volume modulation. Result in current volume to be back at 20%.
# - Moving Average thread never stopped even with "Break"

# 11/01/2021
# - changed sd card to SSD SATA disk
# - import acoustics caused error: valueerror: numpy.ndarray size changed, may indicate binary incompatibility. Expected 44 from C header, got 40 from PyObject
# - Need to change the source for sound masking (remove dependency to other modules)
# - Moving average thread still not breaking,

# 11/03/2021 and 11/04/2021
# - Add "Stop" signal to terminate the both sound modulation and movign average calculation when mic stopped running
# - Used multiprocessing to allow parallel run and used mp.queue 
# - need to figure out how to stop whitenoise from playing when mic is done
# - error that occurs frequently which will result in 0 values put into the ref/err mic--> stop calculation of moving average
#   : had to rerun multiple times
#   python3: src/common/pa_front.c:235: InitializeHostApis: Assertion `hostApi->info.defaultInputDevice < hostApi->info.deviceCount' failed.

# 11/09/2021
# solve the hostApis because the drivers were not deleted since I hard stop it. Not properly stop the processes/threads
# combined the run_ref_mic() to ref_mic, but raised input_overflow error.

# 11/15/2021
# Input overflow can be avoided with 48kHz as the sampling rate and after each stream.read,
# the frames buffer need to be emptied
# 

# 21/12/2021
# Callback can stop the audio recording and playing with specified time in seconds.
# How to make it so it stops when the patient turn it off?
# If the switch is off, then the entire thing will stop, so what would be the best duration?
# Considering the system will be used at night, safe assumption will be 13 hours = 13*60*60 = 46,800s
# To test, let's do 30-mins, 1-hr, 5-hr, and 12-hr tests
# Testing for 120s
# Error handling:
# For micthread and whitenoise: need to create error handling for when invalid number of channels.
# Invalid number of channels means that the mics or/and speaker were not detected. Usually I have to disconnect
# and connect them back to raspi.
# Today, speaker is not detected although after being unplug: I think I broke the speaker
# before that, the volume modulation was not able to control the system volume. They were not the same
# Tested for 120s, but the volume modulation never stopped

# 01/04/2022
# The overall codes are successful for any time period.
# attention: if the absolute volume difference is smaller than 100 then there will be no changes in volume
#            where below is not printed: 
#                           Simple mixer control 'Master',0
#                           Capabilities: pvolume pswitch pswitch-joined
#                           Playback channels: Front Left - Front Right
#                           Limits: Playback 0 - 65536
#                           Mono:
#                           Front Left: Playback 6554 [10%] [on]
#                           Front Right: Playback 6554 [10%] [on]
#
# Action needed: figure out "v_threshold" value that is necessary for the change in volume
# Observation: if the printing of the vol_mod and volume difference continue even after the whitenoise done playing
