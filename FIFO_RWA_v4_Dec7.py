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

from datetime import datetime
import wave

import csv

# Stop signal handler by Ctrl-C
stop_event = mp.Event()
# with SSH it doesnt wokrk :(

# Constants for audio devices
FORMAT  = pyaudio.paInt16    # 24-bit the mic is 24-bit with sample rate of 96kHz
CHANNELS = 1                 # number of audio streams to use. Since there is one speaker and one mic, use 2 streams
RATE = 48000                # 48kHz since mic is specific at 48kHz
FRAMES_PER_BUFFER = 1024    # number of frames the speaker is taking in 
WIDTH = 2

filename = datetime.now().strftime('%b_%d_%H_%M_%S_InternalSoundbyte.wav')

def prepare_file(fname):
    wf = wave.open(fname, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(WIDTH)
    wf.setframerate(RATE)
    return wf

# calculate RMS of data chunk
def rms(data):
    if len(data) == 1: return print('data length =1')
    fromType = np.int16
    d = np.frombuffer(data,fromType).astype(np.float) # convert data from buffer from int16 to float to calculate rms
    rms = np.sqrt(np.mean(d**2))
    return abs(int(rms))

def ref_mic(p, q1, stop_event):   
    
    def callback(in_data, frame_count, time_info, status):
            data = rms(in_data)
#            print("RMS of 2048: ",data)
            q1.put(data)
#             print("q1:", q1.get())
            return in_data, pyaudio.paContinue
        
    stream2 = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        frames_per_buffer=FRAMES_PER_BUFFER,
        input=True,
        input_device_index=1,
        stream_callback = callback)
    
    while not stop_event.wait(0):
        # start stream
        stream2.start_stream()
        

    # control how long the stream to record
    # time.sleep(duration)

    # stop stream
    stream2.stop_stream()

    
    stream2.close()
#     p.terminate()
    
    # Send signal it stopped recording
#    q1.put("Stop")
    
def error_mic(p, q2, stop_event):
    wf = prepare_file(filename)
    
    def callback2(in_data2, frame_count2, time_info2, status2):
            wf.writeframes(in_data2) # record in_data to observe the changes of audio output by loudspeaker
            data2 = rms(in_data2)
#            print("in_data2 length", len(in_data2))
            q2.put(data2)
#             print("q2:", q2.get())
            return in_data2, pyaudio.paContinue
        
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        frames_per_buffer=FRAMES_PER_BUFFER,
        input=True,
        input_device_index=2,
        stream_callback = callback2)
    
    while not stop_event.wait(0):
        # start stream
        stream.start_stream()

    # control how long the stream to record
    #time.sleep(duration)

    # stop stream
    stream.stop_stream()
        
    
    stream.close()
    wf.close()
#     p.terminate()
    
#    q2.put("Stop")

def device_check():
    p = pyaudio.PyAudio()
    devices = []
    
    for ii in range(p.get_device_count()):
        devices.append(p.get_device_info_by_index(ii).get('name'))
        print(p.get_device_info_by_index(ii).get('name'))
    
    return devices

def Multithread_mic(p,q1, q2, stop_event):

    t1 = threading.Thread(target=ref_mic, args=(p,q1,stop_event))
    t2 = threading.Thread(target=error_mic, args=(p,q2,stop_event))
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    p.terminate()
    print("Mic recording is stopped")




#######################################################################################################################################    
# Second Thread for simultaneous calculate the moving average of compiled RMS values
def Moving_Average(q1, q2, q3, q4, stop_event, window= 10):
    
    ref = []
    err = []    
    
    time.sleep(0.5) # allow the q's fill up apparently until 7 data points only after 1s, so I put 2s to get more data 
    print("size: ", q1.qsize(), q2.qsize()) 
    
    while q1.qsize()> 0 and q2.qsize()> 0 and not stop_event.wait(0.5):  #check if the qs are not empty
        
        print('Moving Average Started')
        
        # Put first Window-1 to be the same number as non-averaged rms number
        for n in range(0,window):
                ref.append(q1.get())
                err.append(q2.get())
                q3.put(ref[n])
                q4.put(err[n])
#                print("1st Window",q1.qsize(),q2.qsize())
                
        #Calculate the mean of first (window)
        Mprev_ref = np.mean(ref)
        Mprev_err = np.mean(err)
        
        # Put the means at the window'th position
        q3.put(Mprev_ref)
        q4.put(Mprev_err)
#        print("1st Mean",q3.qsize(),q4.qsize())

        #empty ref and err
        ref = []
        err = []
        
        print('Done first window')
#        print(q1.qsize(), q2.qsize())
        
        
        while not stop_event.wait(0.5):
#            print("Q1 & Q2 IN",q1.qsize(),q2.qsize())
            
#             getQ1 = q1.get()
#             getQ2 = q2.get()
#            print("getQ1:",getQ1,"GetQ2:",getQ2)
            # Calculate next one step window of the data
            Mnew_ref = Mprev_ref + (q1.get() - Mprev_ref)/window
            Mnew_err = Mprev_err + (q2.get() - Mprev_err)/window
#             print(Mnew_ref, Mnew_err)
#            print("Q1 & Q2 OUT", q1.qsize(), q2.qsize())
 
            # New mean becomes the previous mean
            Mprev_ref = Mnew_ref
            Mprev_err = Mnew_err
#            print("Mprev_ref:",Mprev_ref)

            # Save the data in the respective queues
            q3.put(Mprev_ref)
            q4.put(Mprev_err)

#            print("q3 and q4 IN:", q3.qsize(),q4.qsize())
        print('Im out')
  
    print('Moving Average Stopped')
    
    
    
    
    
#####################################################################################################################
# Third Thread for simultaneous volume modulation
def main_volume_modulation(q3, q4, volume_value, stop_event,vol_threshold, W=10):
    file = datetime.now().strftime('%b_%d_%H_%M_%S_volume_difference_baseline.csv')
    
    time.sleep(10) # wait for moving average to complete calculate and put data into q3 and q4
    
    print('volume modulation started')
#     print('shared volume:', volume_value.value)
    
    current_volume = volume_value.value # initializes current volume
    
    
    # cyclical linear ramp from 0 to 100
    while q3.qsize()> 0 and q4.qsize()> 0 and not stop_event.wait(0.5):
    
#        getQ3 = q3.get()
#        getQ4 = q4.get()
#         print("Q3 and Q4 size IN:", q3.qsize(),q4.qsize())
#         volume_value.value = (volume_value.value + 30) % 100
        
        difference = q3.get() - q4.get()  # getQ3 - getQ4    
#        print("Q3 and Q4 OUT",q3.qsize(),q4.qsize())
        volume_value.value = comparator(file, difference, current_volume, W, vol_threshold, nu=1)
        
        current_volume = volume_value.value # set the "current_volume" in modulating_volume function into new_volume because we always get 21, 19, 20
        
   
    print('volume modulation stopped')
    
def comparator(file, difference, current_vol, window=10, v_threshold=100, nu=1):
    # nu : the step size of volume being increased or decreased, in percent, ex: 1 = 1%
    # v_threshold : upper limit of the difference between the mics values
    # return: new volume
    # new volume must not be more than 100 and less than 10
    
    #initialize new volume
    new_vol = current_vol
    
    # if the difference is within [-100, 100] don't change volume
    if difference >= -v_threshold and difference <= v_threshold:
       new_vol = current_vol
       
       print('same baseline', 'volume:', new_vol, 'difference', difference)
    
    elif difference < -v_threshold: # reference mic has smaller volume than error mic, lower the volume by nu
        new_vol = current_vol - nu
        print('ref smaller', 'volume:', new_vol, 'difference', difference)
    
    elif difference > v_threshold: # reference mic is greater than error mic, then increase the volume by nu
        new_vol = current_vol + nu
        print('error smaller', 'volume:', new_vol, 'difference', difference)
    
    #   save data of volume difference in csv file
    file = open(file,'a')
    writer = csv.writer(file)
    writer.writerow(['difference:', difference, 'new volume:', new_vol])
    file.close()
    
    return new_vol
################################################################################################################################################    
# Generating White Noise, y(n)

# NONBLOCKING MODE    
def whitenoise(volume_value):
    
     ##### minimum needed to read a wave #############################
     # open the file for reading.
    WF = wave.open('BrownNoise_60s.wav', 'rb')
    
    
#     print('volume value', volume_value.value)
     
    def callback_speaker(in_data, frame_count, time_info, status):
#          volume_value.value = (volume_value.value + 1) % 100
         data = WF.readframes(frame_count)
         data = set_volume(data,volume_value.value)
         return data, pyaudio.paContinue
     
     #create an audio object
    p2 = pyaudio.PyAudio()
     
     # open stream based on the wave object which has been input
    stream3 = p2.open(format=p2.get_format_from_width(WF.getsampwidth()),
                     channels = WF.getnchannels(),
                     rate = WF.getframerate(),
                     output=True,
                     output_device_index=0,
                     stream_callback=callback_speaker)
#     
#     
     # start stream
    stream3.start_stream()
    print("speaker playing")
     
     # control how long the stream to play
    time.sleep(10)
#         
#         # stop stream
#         
    stream3.stop_stream()
#         wf.rewind()
         
    print('speaker stopped')    
     # cleanup stuff
    stream3.close()
#     
     # close PyAudio
    p2.terminate()
     
    WF.close()
  
def set_volume(datalist,volume):
    """ Change value of list of audio chunks """
#     print('calclated output volume: ', volume)
    if volume >= 0 and volume <= 100: #only changes the volume when volume is within [0,100]
    
        sound_level = (volume / 100.)
            
        fromType = np.int16
        chunk = np.frombuffer(datalist,fromType).astype(np.float) 

        chunk = chunk * sound_level
    #     print(chunk)
        
        datalist = chunk.astype(np.int16)
    #     print(datalist)
    elif volume < 0:
        sound_level = (0/100.0)
        fromType = np.int16
        chunk = np.frombuffer(datalist,fromType).astype(np.float)
        chunk = chunk*sound_level
        datalist = chunk.astype(np.int16)
    
    elif volume > 100:
        sound_level = (100/100.)
        fromType = np.int16
        chunk = np.frombuffer(datalist,fromType).astype(np.float)
        chunk = chunk*sound_level
        datalist = chunk.astype(np.int16)
        
    return datalist


def loop_play(volume_value, stop_event):
    while not stop_event.wait(0):
        #whitenoise_block(q5, CHUNK=1024)
        whitenoise(volume_value)
        
###########################################################################################
def stop(signum, frame):
    global stop_event
    print(f"SIG[{signum}]")
    stop_event.set()
    
############################# Main code ###################################################
def thread_mask():    
    print('Start')
    
    # os shutdown
    #signal.signal(signal.SIGTERM, stop)
    # ctrl-c
    signal.signal(signal.SIGINT, stop)
    
    p = pyaudio.PyAudio()
    
#     # Making sure all devices are recognized first
#     d = device_check()
#     while len(d)<13:
#         time.sleep(1)
#         d = device_check()
#
    
    device_check() # check if all device are recognized
    
    #period = 10
    window = 5
    maxsize = window
    threshold = 10

    q1 = mp.Queue(maxsize)
    q2 = mp.Queue(maxsize)
    q3 = mp.Queue(maxsize)
    q4 = mp.Queue(maxsize)
    
    volume_value = mp.Value('d', 1.0)

    p1 = mp.Process(target=Multithread_mic, args=(p,q1,q2,stop_event))
    p2 = mp.Process(target=loop_play, args=(volume_value, stop_event,))
    p3 = mp.Process(target=Moving_Average, args=(q1, q2, q3, q4, stop_event, window))
    p4 = mp.Process(target=main_volume_modulation, args = (q3,q4,volume_value, stop_event,threshold, window))
    
    
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
# meaning the mic, speaker, whitenoise thread finished first then the volume modulation ended.
# Action needed: stop volume modulation when all all these three processes stop.

# 01/06/2022
# Stop signal is handled, not yet tested

#01/11/2022
# stop signal worked for all processes, just need to wait for the 1mins whitenoise finish playing then it will be done
# loop playing whitenoise using additional thread is needed. There is no way blocking or non-blocking mode can rewind and play
# infinitely without defining how long it should play
# the system and speaker volume are not in sync.

# 01/19/2022
# speaker produce a choppy sound

# 01/20/2022
# Produce continuous sound
# However, higher volume, there is a crackling sound
# Test putting the error or reference mic closer to the speaker to see if they will change the volume up/down. Need to test some more
# print statement on the set_volume() does not stop even when Ctrl-C is clicked. Need to change that! If not, will need to force
# stop which eventually made the devices lost. Will require reboot.

# 02/17/2022
# the ssh doesnt allow for stop-event to work
# the queue buffer increased in size rather than equal rate of get.() and put.()

# 03/02/2022
# window size = maxsize of queue faster response
# threshold changed from 30 to 10
# however, when the ambient noise get lowered down, the reference mic is smaller in value, pushes the comparator to reduce the volume by 1
# when the new volume passed 0 and become negative volume, it will cause a build up of negative value to be catch up on when the ambinet noise
# increase in level. Need to set when new volume equal to 0, the next new volume also equal to 0 if the difference is still negative.
