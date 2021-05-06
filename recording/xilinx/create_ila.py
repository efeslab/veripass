# -*- coding: utf-8 -*-
"""
Created on Wed May  5 17:17:09 2021

@author: Haoyang Zhang
"""

import sys

name = sys.argv[1]
depth = int(sys.argv[2])


fp_instru = open('instrumented.txt')
fp_tcl = open(name)
fp_write = open('ila_0_emulated.v', 'w')


tclfile = fp_tcl.readline()
tclfile = fp_tcl.read()
tclfile = tclfile.split('[')[1]
tclfile = tclfile.split(']')[0]
tclfile = tclfile.split('CONFIG.C_NUM_OF_PROBES {')[1]
probe_num_str = tclfile.split('}')[0]
probe_num = int(probe_num_str)
tclfile = tclfile.split(probe_num_str+'} ')[1]
tcl_list = tclfile.split(' ')


probe_width_list = []
data_in_bits = 0
for i in range(probe_num):
    width = int(tcl_list[6*i+1][1:len(tcl_list[6*i+1])-1])
    data_in_bits += width
    probe_width_list.append(width)


fp_write.write('module ila_0_emulated (\n')
fp_write.write('    input clk\n')

for i in range(probe_num):
    if probe_width_list[i]==1:
        line = '  , input ' + 'probe' + str(i) + '\n'
    else:
        line = '  , input [' + str(probe_width_list[i]-1) + ':' + str(0) +'] probe' + str(i) + '\n'
    fp_write.write(line)

fp_write.write(');\n')
fp_write.write('\n')
fp_write.write('    integer buffer;\n')
fp_write.write('    initial begin\n')
fp_write.write('        buffer = $fopen("w_buffer.txt");\n')
fp_write.write('        $fdisplay(buffer, "%d %d", ' + str(data_in_bits) + ', ' + str(depth) +');\n')
fp_write.write('    end\n')
fp_write.write('\n')

fp_write.write('    always @(negedge clk) begin\n')
data_in = '{'
for i in range(probe_num-1):
    data_in += 'probe' + str(i) +', '
data_in += 'probe' + str(probe_num-1) + '}'
fp_write.write('        $fdisplay(buffer, "%b %h", 1\'b1, '+ data_in +');\n')
fp_write.write('    end\n')
fp_write.write('\n')
fp_write.write('\n')
fp_write.write('endmodule\n')

instru = ''
instru = fp_instru.read()
instru_w = instru + 'ila_0_emulated.v\n'
fp_instru.close()
print('The verilog file for ila generated successfully!')

fp_instru_w = open('instrumented.txt','w')
fp_instru_w.write(instru_w)