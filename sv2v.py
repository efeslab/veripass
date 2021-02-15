import os
import sys
import pathlib
import argparse
from verilator import *
from recordpass import *
#from livetest import *

from pyverilog.vparser.parser import VerilogCodeParser
from pyverilog.dataflow.modulevisitor import ModuleVisitor
from pyverilog.dataflow.signalvisitor import SignalVisitor
from pyverilog.dataflow.bindvisitor import BindVisitor
import pyverilog.utils.util as util

from dataflowpass import dataflowtest

parser = argparse.ArgumentParser(description="Translate SystemVerilog to Readable Verilog")
parser.add_argument("--top", dest="top_module", help="top module name")
parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator")
parser.add_argument("-o", dest="output", help="output path")
parser.add_argument("--split", default=False, action="store_true", dest="split", help="whether to split variable")

args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))
print("Split Variables: {}".format(args.split))

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file)
if args.split:
    ast = v.get_splitted_ast()
else:
    ast = v.get_ast()

#ri = RecordInstrument("xilinx", ast, v.get_splitted_typetable(), v.get_splitted_used_vars(), "pClk")
#ri.add_data("ccip_std_afu__DOT__data_rx__BRA__511__03A480__KET__")
#ri.add_data("ccip_std_afu__DOT__data_rx__BRA__479__03A448__KET__")
#ri.add_data("ccip_std_afu__DOT__data_rx__BRA__447__03A416__KET__")
#ri.add_trigger("ccip_std_afu__DOT__mpf__DOT__mpf_edge_fiu__DOT__b__DOT__c1_fifo__DOT__fifo__DOT__data__DOT__rbw__DOT__wen_q")
#ri.add_trigger("ccip_std_afu__DOT__mpf__DOT__mpf_edge_fiu__DOT__wr_heap_data__DOT__c0__DOT__data__DOT__m_default__DOT__altsyncram_inst__DOT__i_rden_reg_a")
#ri.generate()
#ast = ri.ast

used_vars = v.get_used_vars()
typetable = v.get_typetable()
#lv = DependVisitor("c0Rx_data")
#lv = DependVisitor(used_vars, typetable, "c0Rx_data")
#lv.visit(ast)

module_visitor = ModuleVisitor()
module_visitor.visit(ast)
modulenames = module_visitor.get_modulenames()
moduleinfotable = module_visitor.get_moduleinfotable()
print(modulenames)
print(moduleinfotable)

signal_visitor = SignalVisitor(moduleinfotable, "ccip_std_afu_wrapper")
signal_visitor.add_blackbox_module("altsyncram")
signal_visitor.start_visit()
frametable = signal_visitor.getFrameTable()
print(frametable)

bind_visitor = BindVisitor(moduleinfotable, "ccip_std_afu_wrapper", frametable, noreorder=False)
bind_visitor.add_blackbox_module("altsyncram")
bind_visitor.start_visit()
dataflow = bind_visitor.getDataflows()
terms = dataflow.getTerms()
binddict = dataflow.getBinddict()

dft = dataflowtest(ast, terms, binddict, "ccip_std_afu_wrapper.c0Rx_data", "ccip_std_afu_wrapper.c1Tx_data")
#dft = dataflowtest(ast, terms, binddict, "ccip_std_afu_wrapper.ccip_std_afu__DOT__data_tx",
#        "ccip_std_afu_wrapper.ccip_std_afu__DOT__data_rx")
termname = util.toTermname("ccip_std_afu_wrapper.c1Tx_data")
#dft.test(termname)
#dft.findDataflow()
dft.find2()

termname = util.toTermname("ccip_std_afu_wrapper.c1Tx_data")
t = terms[termname]
b = binddict[termname]

codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, 'w+') as f:
    f.write(rslt)

#used_vars = v.get_used_vars()
#typetable = v.get_typetable()
#total = 0
#dff = 0
#nodff = 0
#unknown = 0
#for name in used_vars:
#    varref = used_vars[name]
#    varref_dtype = typetable[varref.dtype_id]
#    if varref_dtype.array_len == 0:
#        for i in range(0, varref_dtype.width):
#            total += 1
#            if varref.dff[i] == True:
#                dff += 1
#            elif varref.dff[i] == False:
#                nodff += 1
#            elif varref.dff[i] == None:
#                unknown += 1
#    else:
#        for i in range(0, varref_dtype.array_len):
#            for j in range(0, varref_dtype.width):
#                total += 1
#                if varref.dff[i][j] == True:
#                    dff += 1
#                elif varref.dff[i][j] == False:
#                    nodff += 1
#                elif varref.dff[i][j] == None:
#                    unknown += 1
#print(total, dff, nodff, unknown)
#
#
