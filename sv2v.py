import os
import sys
import pathlib
import argparse
import time
from verilator import *
from passes.IdentifierRefPass import IdentifierRefPass
from passes.TypeInfoPass import TypeInfoPass
from passes.WidthPass import WidthPass
from passes.CanonicalFormPass import CanonicalFormPass
from passes.TaskSupportPass import TaskSupportPass
from passes.ArraySplitPass import ArraySplitPass
from passes.Logic2RegPass import Logic2RegPass
from passes.RefClockPass import RefClockPass
from passes.BoundaryCheckPass import ArrayBoundaryCheckPass
from passes.common import PassManager

from pyverilog.vparser.parser import VerilogCodeParser
import pyverilog.utils.util as util

parser = argparse.ArgumentParser(description="Translate SystemVerilog to Readable Verilog")
parser.add_argument("--top", dest="top_module", help="top module name")
parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator")
parser.add_argument("-o", dest="output", help="output path")
parser.add_argument("--split", default=False, action="store_true", dest="split", help="whether to split variable")
parser.add_argument("--tasksupport", default=False, action="store_true", help="whether to run TaskSupportPass")

args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))
print("Split Variables: {}".format(args.split))

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file)
ast = v.get_ast()

pm = PassManager()
#pm.register(Logic2RegPass)
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.register(CanonicalFormPass)
pm.register(ArrayBoundaryCheckPass)
if args.tasksupport:
    pm.register(TaskSupportPass)
#pm.register(ArraySplitPass)
pm.runAll(ast)

#for name in pm.state.array_access_info:
#    print(name, pm.state.array_access_info[name])

codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, 'w+') as f:
    f.write(rslt)
