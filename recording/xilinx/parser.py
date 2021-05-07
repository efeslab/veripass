# -*- coding: utf-8 -*-
"""
Created on Mon May  3 19:50:09 2021

@author: Haoyang Zhang
"""

import sys

count = int(sys.argv[1])
name = sys.argv[2]

fp_buffer = open('w_buffer.txt')
fp_width = open(name+'.v.widthinfo.txt')
fp_display = open(name +'.v.displayinfo.txt')
fp_write = open('reconstruct.txt','w')


buffer = fp_buffer.read()
buffer_list = buffer.split()
data_bits = int(buffer_list[0])
del buffer_list[0]
depth = int(buffer_list[0])
del buffer_list[0]

for i in range(len(buffer_list)):
    buffer_list[i] = bin(int(buffer_list[i],16)) #change to binary
    buffer_list[i] = buffer_list[i][2:] # delete "0b"
for i in range(int(len(buffer_list)/2)): # refill the possible '0's at left to let them all have data_bits width
    if len(buffer_list[2*i+1])!=data_bits:
        rest = data_bits - len(buffer_list[2*i+1])
        for j in range(rest):
            buffer_list[2*i+1] = '0' + buffer_list[2*i+1]
for i in range(int(len(buffer_list)/2)): #transform buffer_list to a list of lists each means one line in buffer
    new_list = []
    new_list.append(buffer_list[2*i]) # the left one is sla_triggered signal 
    new_list.append(buffer_list[2*i+1]) # the right one is data in binary
    buffer_list[i] = new_list
buffer_list = buffer_list[:int(len(buffer_list)/2)]
triggered_place = depth
for i in range(len(buffer_list)):
    if buffer_list[i][0]=='1':
        triggered_place = i
        break

buffer_start = 0
buffer_end = 0
if triggered_place-count <= 0:
    buffer_start = 0
else:
    buffer_start = triggered_place-count
if triggered_place+depth-count >= len(buffer_list):
    buffer_end = len(buffer_list)
else:
    buffer_end = triggered_place+depth-count
buffer_list = buffer_list[buffer_start:buffer_end]
#print(buffer_list)


display_list = fp_display.read().split('\n')
cond_num = len(display_list) - 1
display_list.pop()
#print(cond_num)
for i in range(cond_num): # each entry of this list means a display statement
    display_list[i] = display_list[i].split('"')[1:] # the left one is the string in ""
    display_list[i][0] = display_list[i][0].replace('%b', '%x')
    display_list[i][0] = display_list[i][0].replace('%h', '%x')
    display_list[i][0] = display_list[i][0].replace('%0b', '%x')
    display_list[i][0] = display_list[i][0].replace('%0h', '%x')
    display_list[i][0] = display_list[i][0].replace('%0t', '%d')
    display_list[i][1] =  display_list[i][1].split(' ')
    display_list[i][1].pop()
    new_list = []
    for j in range(len(display_list[i][1])): 
        if display_list[i][1][j]!=',':
            new_list.append(display_list[i][1][j])
    length = len(new_list[len(new_list)-1])
    new_list[len(new_list)-1] = new_list[len(new_list)-1][:length-1]
    if len(new_list[len(new_list)-1]) == 0:
        new_list.pop()
    #print(new_list)
    display_list[i][1] = new_list # the right one is a list containing the data names
    for j in range(len(display_list[i][1])):
        if display_list[i][1][j]=='$time':
            display_list[i][1][j] = 'TASKPASS_cycle_counter' # replace "$time" with cycle_counter
#print(display_list)


width_list = fp_width.read().split()
i = 0
dict_data = {} # we use a dictionary, the key is the name, the value is a list
start_index = cond_num
while i < len(width_list):
    value_list = []
    value_list.append(int(width_list[i+1])) # Its first component is the width
    value_list.append(start_index) # Its second component is the start index
    start_index += int(width_list[i+1])
    dict_data[width_list[i]] = value_list
    i+=2
#print(dict_data);
   
for buffer_entry in buffer_list:
    for cond_index in range(cond_num):
        if buffer_entry[1][cond_index]=='1':
            tup = ()
            for name in display_list[cond_index][1]:
                value = int(buffer_entry[1][dict_data[name][1]:(dict_data[name][1]+dict_data[name][0])],2)
                new_tup = (value,)
                tup += new_tup
            line = display_list[cond_index][0] % tup
            line = line +'\n'
            fp_write.write(line)

print('Done reconstructing displays! The result is in "reconstruct.txt"')
            