import os
import sys
import pathlib
import argparse
import time
from verilator import *
from recordpass import *
from passes.IdentifierRefPass import IdentifierRefPass
from passes.TypeInfoPass import TypeInfoPass
from passes.WidthPass import WidthPass
from passes.CanonicalFormPass import CanonicalFormPass
from passes.TaskSupportPass import TaskSupportPass
from passes.common import PassManager
#from livetest import *

#sys.path.append(str(pathlib.Path(__file__).parent.absolute()/"build"/"lib.linux-x86_64-3.9"))
start = time.time()

from pyverilog.vparser.parser import VerilogCodeParser
from pyverilog.dataflow.modulevisitor import ModuleVisitor
from pyverilog.dataflow.signalvisitor import SignalVisitor
from pyverilog.dataflow.bindvisitor import BindVisitor
import pyverilog.utils.util as util

from dataflowpass import dataflowtest

from model.altsyncram_simple_model import AltsyncramSimpleModel
from model.dcfifo_simple_model import DcfifoSimpleModel

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
ast = v.get_ast()

#ri = RecordInstrument("xilinx", ast, v.get_splitted_typetable(), v.get_splitted_used_vars(), "pClk")
#ri.add_data("ccip_std_afu__DOT__data_rx__BRA__511__03A480__KET__")
#ri.add_data("ccip_std_afu__DOT__data_rx__BRA__479__03A448__KET__")
#ri.add_data("ccip_std_afu__DOT__data_rx__BRA__447__03A416__KET__")
#ri.add_trigger("ccip_std_afu__DOT__mpf__DOT__mpf_edge_fiu__DOT__b__DOT__c1_fifo__DOT__fifo__DOT__data__DOT__rbw__DOT__wen_q")
#ri.add_trigger("ccip_std_afu__DOT__mpf__DOT__mpf_edge_fiu__DOT__wr_heap_data__DOT__c0__DOT__data__DOT__m_default__DOT__altsyncram_inst__DOT__i_rden_reg_a")
#ri.generate()
#ast = ri.ast

'''
used_vars = v.get_used_vars()
typetable = v.get_typetable()

module_visitor = ModuleVisitor()
module_visitor.visit(ast)
modulenames = module_visitor.get_modulenames()
moduleinfotable = module_visitor.get_moduleinfotable()

altsyncram = AltsyncramSimpleModel()
dcfifo = DcfifoSimpleModel()
signal_visitor = SignalVisitor(moduleinfotable, "ccip_std_afu_wrapper")
signal_visitor.addBlackboxModule("altsyncram", altsyncram)
signal_visitor.addBlackboxModule("dcfifo", dcfifo)
#signal_visitor.addBlackboxModule("scfifo")
signal_visitor.start_visit()
frametable = signal_visitor.getFrameTable()

bind_visitor = BindVisitor(moduleinfotable, "ccip_std_afu_wrapper", frametable, noreorder=False, ignoreSyscall=True)
bind_visitor.addBlackboxModule("altsyncram", altsyncram)
bind_visitor.addBlackboxModule("dcfifo", dcfifo)
#bind_visitor.addBlackboxModule("scfifo")
bind_visitor.start_visit()
dataflow = bind_visitor.getDataflows()
terms = dataflow.getTerms()
binddict = dataflow.getBinddict()

dft = dataflowtest(ast, terms, binddict,
        "ccip_std_afu_wrapper.c0Rx_data", "ccip_std_afu_wrapper.c0Rx_rspValid", "ccip_std_afu_wrapper.c1Tx_data",
        "ccip_std_afu_wrapper.pck_cp2af_softReset")
dft.addBlackboxModule("altsyncram", altsyncram)
dft.addBlackboxModule("dcfifo", dcfifo)
dft.find2()

termname = util.toTermname("ccip_std_afu_wrapper.c1Tx_data")
t = terms[termname]
b = binddict[termname]
'''
pm = PassManager()
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.register(CanonicalFormPass)
pm.register(TaskSupportPass)
pm.runAll(ast)

codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, 'w+') as f:
    f.write(rslt)

end = time.time()
print(end - start)

print("$display args:")
for id, arg in enumerate(pm.state.display_args):
    print("{}: {}".format(id, codegen.visit(arg)))
