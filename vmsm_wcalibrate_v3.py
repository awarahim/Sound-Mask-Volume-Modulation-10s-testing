#!/usr/bin/python3
# -*- coding:utf-8 -*-
import logging

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


# For logging
logging.basicConfig(filename='vmsm_Log.txt', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Stop signal handler by Ctrl-C
stop_event = mp.Event()
# with SSH it doesnt wokrk :(

# Constants for audio devices
FORMAT  = pyaudio.paInt16    # 24-bit the mic is 24-bit with sample rate of 96kHz
CHANNELS = 1                 # number of audio streams to use. Since there is one speaker and one mic, use 2 streams
RATE = 48000                # 48kHz since mic is specific at 48kHz
FRAMES_PER_BUFFER = 1024    # number of frames the speaker is taking in 
WIDTH = 2


## helper function ##
def device_check():
    p = pyaudio.PyAudio()
    devices = []
    
    for ii in range(p.get_device_count()):
        devices.append(p.get_device_info_by_index(ii).get('name'))
        print(p.get_device_info_by_index(ii).get('name'))
    
    return devices

def prepare_wavfile(p):
    fname = datetime.now().strftime('%b_%d_%H_%M_%S_InternalSoundbyte.wav')
    wf = wave.open(fname, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(4)
    wf.setframerate(RATE)
    return wf

# calculate RMS of data chunk
def rms(data):
    if len(data) == 1: return print('data length =1')
    fromType = np.int16
    d = np.frombuffer(data,fromType).astype(np.float) # convert data from buffer from int16 to float to calculate rms
    rms = np.sqrt(np.mean(d**2))
    return abs(int(rms))
    
    
##### Functional functions ######
def ref_mic(p, q1, stop_event):   
    logging.info('ref mic running...')
    print('ref mic running...')
    ref_fname = datetime.now().strftime('%b_%d_%H_%M_%S_ref_data.csv')
    
    def callback(in_data, frame_count, time_info, status):
            data = rms(in_data)
#            print("RMS of 2048: ",data)
            q1.put(data)
            with open(ref_fname, 'a') as f:
                csvwriter = csv.writer(f)
                csvwriter.writerow(['time', datetime.now().strftime('%H:%M:%S:%f'), 'data', str(data)])
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
    
    try:
        while not stop_event.wait(1):
            # start stream
            stream2.start_stream()
       
    except KeyboardInterrupt: # not really working

        stream2.stop_stream()
        stream2.close()
        logging.info('ref mic is stopped')
        print('ref mic is stopped')
    
def error_mic(p, q2, stop_event):
    wf = prepare_wavfile(p)
    print('error mic running...')
#    logging.info('error mic running...')
    err_fname = datetime.now().strftime('%b_%d_%H_%M_%S_error_data.csv')
    def callback2(in_data2, frame_count2, time_info2, status2):
            wf.writeframes(in_data2) # record in_data to observe the changes of audio output by loudspeaker
            data2 = rms(in_data2)
#            print("in_data2 length", len(in_data2))
            q2.put(data2)
#             print("q2:", q2.get())
            with open(err_fname, 'a') as w:
                csvwriter2 = csv.writer(w)
                csvwriter2.writerow(['time', datetime.now().strftime('%H:%M:%S:%f'), 'data', str(data2)])
                
            return in_data2, pyaudio.paContinue
        
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        frames_per_buffer=FRAMES_PER_BUFFER,
        input=True,
        input_device_index=3,
        stream_callback = callback2)
    try:
            
        while not stop_event.wait(1): # data coming in is really fast, use 1s for the wait
            # start stream
            stream.start_stream()
        logging.info('error mic is stopped')
        print('error mic is stopped')
    except KeyboardInterrupt: # not really working
        stream.stop_stream()
        stream.close()
        wf.close()
        
    


def multithread_mic(q1, q2, stop_event):
    p = pyaudio.PyAudio()
    t1 = threading.Thread(target=ref_mic, args=(p,q1,stop_event))
    t2 = threading.Thread(target=error_mic, args=(p,q2,stop_event))
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    p.terminate()
    logging.info("Mic recording is stopped")
    print('Mic recording is stopped')



#######################################################################################################################################    
# Second Thread for simultaneous calculate the moving average of compiled RMS values
def moving_average(q1, q2, q3, q4, stop_event, window= 10):
    
    ref = []
    err = []    
    
    time.sleep(0.5) # allow the q's fill up apparently until 7 data points only after 1s, so I put 2s to get more data 
    logging.info("initial Q1 and Q2 size: " + str(q1.qsize()) + ' ' + str(q2.qsize())) 
    print('Initial Q1 Q2 size:', q1.qsize(), q2.qsize())

    while q1.qsize()> 0 and q2.qsize()> 0 and not stop_event.wait(0.1):  #check if the qs are not empty
        
        logging.info('Moving Average Started')
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
        
        logging.info('Done first window')
#        print(q1.qsize(), q2.qsize())
        
        
        while not stop_event.wait(0.1):
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
#         print('Im out')
  
    logging.info('Moving Average Stopped')
    print('Moving Average Stopped')
    
    
    
    
#####################################################################################################################
# Third Thread for simultaneous volume modulation

def vol_diff_calibrate(q3,q4, vol_threshold, stop_event, duration=1*60):
   
    buffer = []
    start = time.time()
    elapsed = 0

    logging.info('calibrating... ' + str(datetime.now()))
    print('calibrating...', datetime.now())

    while elapsed < duration and not stop_event.wait(0.1):
        difference = q3.get() - q4.get()
        buffer.append(difference)
        current = time.time()
        elapsed = current - start
    mean = abs(np.mean(buffer)) # must only give positive threshold
    logging.info('current vol_threshold: ' + str(vol_threshold))
    print('current vol_threshold:', vol_threshold)

    vol_threshold = round(mean)
    logging.info('done calibrated threshold: ' + str(vol_threshold))
    print('done calibrated threshold:', vol_threshold)
    return vol_threshold

def main_volume_modulation(q3, q4, delta, volume_value, stop_event,vol_threshold, duration, W=10):
    file = datetime.now().strftime('%b_%d_%H_%M_%S_VMSM_test.csv')
    
    #time.sleep(1) # wait for moving average to complete calculate and put data into q3 and q4
    
    vol_threshold.value = vol_diff_calibrate(q3,q4, vol_threshold.value, stop_event, duration)
    
#     time.sleep(1)
    logging.info('volume modulation started')
    print('volume modulation started')

#     print('shared volume:', volume_value.value)
    
    current_volume = volume_value.value # initializes current volume
    
    
    # cyclical linear ramp from 0 to 100
    print('q3 & q4 size:',q3.qsize(), q4.qsize())
    while q3.qsize()> 0 and q4.qsize()> 0 and not stop_event.wait(0.1):
    
#        getQ3 = q3.get()
#        getQ4 = q4.get()
#         print("Q3 and Q4 size IN:", q3.qsize(),q4.qsize())
#         volume_value.value = (volume_value.value + 30) % 100
        
        difference = q3.get() - q4.get()  # getQ3 - getQ4    
#        print("Q3 and Q4 OUT",q3.qsize(),q4.qsize())
        # "Learning rate" / "sensitivity" of volume adjustment
        delta = delta # The larger this number, the longer it should take to reach the target volume
        nu = abs(difference / delta)
#         print('NU:', nu)
        volume_value.value = comparator(file, difference, current_volume, W, vol_threshold.value, nu)
#         logging.info('volume step size:' + str(nu))
        
        current_volume = volume_value.value # set the "current_volume" in modulating_volume function into new_volume because we always get 21, 19, 20
        
   
    logging.info('volume modulation stopped')
    print('volume modulation stopped')
    
def comparator(file, difference, current_vol, window=10, v_threshold=100, nu=1):
    # nu : the step size of volume being increased or decreased, in percent, ex: 1 = 1%
    # v_threshold : upper limit of the difference between the mics values
    # return: new volume
    # new volume must not be more than 100 and less than 10
    
    #initialize new volume
    new_vol = current_vol
    
    # if the difference is within [-100, 100] don't change volume
    if difference >=( -v_threshold-5.0)  and difference <= (v_threshold+5.0):
       new_vol = current_vol
       logging.info('same baseline,' + ' calc volume: ' + str(new_vol) + ' difference: ' + str(difference))
       print('same baseline, calc volume:', new_vol, 'difference', difference)
 
    elif difference < (-v_threshold-5.0): # reference mic has smaller volume than error mic, lower the volume by nu
        new_vol = current_vol - nu
        logging.info('ref smaller,' + ' calc volume: ' + str (new_vol) + ' difference: ' + str(difference))
        print('ref smaller, calc volume:', new_vol, 'difference:', difference)
    
    elif difference > (v_threshold+5.0): # reference mic is greater than error mic, then increase the volume by nu
        new_vol = current_vol + nu
        logging.info('error smaller,' + ' calc volume: ' + str(new_vol) + ' difference: ' + str(difference))
        print('error smaller, calc volume:', new_vol, 'difference', difference)
    
    if new_vol <5:
        new_vol = 5
        logging.info('volume became negative, so set it to ' + str(new_vol))
        print('volume lowered to minimum 5')

    elif new_vol > 100:
        new_vol = 100
        logging.info('volume maxed to 100')
        print('volume maxed to 100')
        
    #   save data of volume difference in csv file
    file = open(file,'a')
    writer = csv.writer(file)
    writer.writerow(['time',datetime.now().strftime('%H:%M:%S:%f') ,'difference:', difference, 'new volume:', new_vol])
    file.close()
    
    return new_vol
################################################################################################################################################    
# Generating White Noise, y(n)

# NONBLOCKING MODE    
def whitenoise(volume_value, stop_event):
    
     ##### minimum needed to read a wave #############################
     # open the file for reading.
    WF = wave.open('BrownNoise_60s.wav', 'rb')
    
    
#     print('volume value', volume_value.value)
     
    def callback_speaker(in_data, frame_count, time_info, status):
#          volume_value.value = (volume_value.value + 1) % 100
         data = WF.readframes(frame_count)
#         tic = time.time()
         data = set_volume(data,volume_value.value)
#         toc = time.time() - tic
#         print('time taken to set volume:', toc)
         return data, pyaudio.paContinue
     
     #create an audio object
    p2 = pyaudio.PyAudio()
     
     # open stream based on the wave object which has been input
    stream3 = p2.open(format=p2.get_format_from_width(WF.getsampwidth()),
                     channels = WF.getnchannels(),
                     rate = WF.getframerate(),
                     output=True,
                     output_device_index=1,
                     stream_callback=callback_speaker)
#     
#     
     # start stream
    while not stop_event.wait(0.1):
        stream3.start_stream()
        logging.info("speaker playing")
         
         # control how long the stream to play
        time.sleep(10)
        WF.rewind()  
#         # stop stream
#         
    stream3.stop_stream()
#         wf.rewind()
         
        
#      # cleanup stuff
    stream3.close()
# #     
#      # close PyAudio
#    p2.terminate() dont terminate while in the loop since it will have more lagging in sound production
     
    WF.close()
      
#     logging.info('speaker stopped')
    logging.info('Speaker completely stopped at ' + str(datetime.now()))
    print('Speaker completely stopped at ', datetime.now())
    
    
    
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
        sound_level = (5/100.0)
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


# def loop_play(volume_value, stop_event):
#     while not stop_event.wait(0.5):
#         #whitenoise_block(q5, CHUNK=1024)
#         whitenoise(volume_value)
# #    stream3.close()
# #    p2.terminate()
#     logging.info('Speaker completely stopped at ' + str(datetime.now()))
#     print('Speaker completely stopped at ', datetime.now())

###########################################################################################
def stop(signum, frame):
    global stop_event
    logging.info(f"SIG[{signum}] " + 'KeyboardInterrupt ' + str(datetime.now()))
    print('KeyboardInterrupt ', datetime.now())
    stop_event.set()


############################# Main code ###################################################
def thread_mask():    

    # os shutdown
    #signal.signal(signal.SIGTERM, stop)
    # ctrl-c
    signal.signal(signal.SIGINT, stop)
    
#     # Making sure all devices are recognized first
#     d = device_check()
#     while len(d)<13:
#         time.sleep(1)
#         d = device_check()
    
    #period = 10
    print('Enter window size:')
    window = int(input())
    logging.info('window size:' + str(window))
    print('Enter max_size:')
    maxsize = int(input())
    logging.info('max Queue size:' + str(maxsize))
    print('Enter delta:')
    delta = int(input())
    logging.info('delta:' + str(delta))
    
    vol_threshold = mp.Value('d', 10.0) # initial value of threshold value
    calibrate_duration = 3*60 # in seconds
    volume_value = mp.Value('d', 5.0)
    
    q1 = mp.Queue(maxsize)
    q2 = mp.Queue(maxsize)
    q3 = mp.Queue(maxsize)
    q4 = mp.Queue(maxsize)
    
    logging.info('Start ' + str(datetime.now()))
    print('Start at ', datetime.now())
    

    p1 = mp.Process(target=multithread_mic, args=(q1,q2,stop_event))
    p2 = mp.Process(target=whitenoise, args=(volume_value, stop_event))
    p3 = mp.Process(target=moving_average, args=(q1, q2, q3, q4, stop_event, window))
    p4 = mp.Process(target=main_volume_modulation, args = (q3,q4,delta,volume_value, stop_event,vol_threshold, calibrate_duration, window))
    
    p1.start()
    p2.start()
    p3.start()
    p4.start()
    
    
    p1.join()
    p2.join()
    p3.join()
    p4.join() 
    
    
    logging.info('End')
    print('Ended at ', datetime.now())
    
#######################################################################################################
   
if __name__ == '__main__':
    thread_mask()
    


## Notes
    # timeout for stop_event.wait(0.1) must be the same for all functions for volume modulation to not have pre-termination.
    # Does timeout cause data to be collected every 0.1s or previously 0.5s? Yes. and stop_event.wait(cannot be blank) 
