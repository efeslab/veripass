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
from passes.ArraySplitPass import ArraySplitPass
from passes.common import PassManager

start = time.time()

from pyverilog.vparser.parser import VerilogCodeParser
from pyverilog.dataflow.modulevisitor import ModuleVisitor
from pyverilog.dataflow.signalvisitor import SignalVisitor
from pyverilog.dataflow.bindvisitor import BindVisitor
import pyverilog.utils.util as util

from dataflowpass import dataflowtest

from model.altsyncram_simple_model import AltsyncramSimpleModel
from model.dcfifo_simple_model import DcfifoSimpleModel
from model.scfifo_simple_model import ScfifoSimpleModel

parser = argparse.ArgumentParser(description="Translate SystemVerilog to Readable Verilog")
parser.add_argument("--top", dest="top_module", help="top module name")
parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator")
parser.add_argument("-o", dest="output", help="output path")
parser.add_argument("--filtered-list", default=None, dest="filtered_list", help="file of ignored signals")

args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file)
ast = v.get_ast()

pm = PassManager()
pm.register(ArraySplitPass)
pm.runAll(ast)

used_vars = v.get_used_vars()
typetable = v.get_typetable()

module_visitor = ModuleVisitor()
module_visitor.visit(ast)
modulenames = module_visitor.get_modulenames()
moduleinfotable = module_visitor.get_moduleinfotable()

altsyncram = AltsyncramSimpleModel()
dcfifo = DcfifoSimpleModel()
scfifo = ScfifoSimpleModel()
signal_visitor = SignalVisitor(moduleinfotable, "ccip_std_afu_wrapper")
signal_visitor.addBlackboxModule("altsyncram", altsyncram)
signal_visitor.addBlackboxModule("dcfifo", dcfifo)
signal_visitor.addBlackboxModule("scfifo", scfifo)
signal_visitor.start_visit()
frametable = signal_visitor.getFrameTable()

bind_visitor = BindVisitor(moduleinfotable, "ccip_std_afu_wrapper", frametable, noreorder=False, ignoreSyscall=True)
bind_visitor.addBlackboxModule("altsyncram", altsyncram)
bind_visitor.addBlackboxModule("dcfifo", dcfifo)
bind_visitor.addBlackboxModule("scfifo", scfifo)
bind_visitor.start_visit()
dataflow = bind_visitor.getDataflows()
terms = dataflow.getTerms()
binddict = dataflow.getBinddict()

dft = dataflowtest(ast, terms, binddict,
        "ccip_std_afu_wrapper.c0Rx_data", "ccip_std_afu_wrapper.c0Rx_rspValid", "ccip_std_afu_wrapper.c1Tx_data",
        "ccip_std_afu_wrapper.pck_cp2af_softReset",
        gephi=True)
dft.addBlackboxModule("altsyncram", altsyncram)
dft.addBlackboxModule("dcfifo", dcfifo)
dft.addBlackboxModule("scfifo", scfifo)
if args.filtered_list != None:
    dft.set_filtered(args.filtered_list)
dft.find2()

# post instrumentation passes, for compilation purpose
pm = PassManager()
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.register(CanonicalFormPass)
pm.register(TaskSupportPass)
#pm.register(ArraySplitPass)
pm.runAll(ast)

codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, 'w+') as f:
    f.write(rslt)

end = time.time()
print(end - start)
