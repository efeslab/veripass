#!/usr/bin/env python3
import os
import sys
import pathlib
import argparse
import time
import re
from verilator import *
from passes.IdentifierRefPass import IdentifierRefPass
from passes.TypeInfoPass import TypeInfoPass
from passes.WidthPass import WidthPass
from passes.CanonicalFormPass import CanonicalFormPass
from passes.ArraySplitPass import ArraySplitPass
from passes.Logic2RegPass import Logic2RegPass
from passes.SimpleRefClockPass import SimpleRefClockPass
from passes.BoundaryCheckPass import ArrayBoundaryCheckPass
from passes.StateMachineDetectionPass import StateMachineDetectionPass
from passes.PrintTransitionPass import PrintTransitionPass, TransRecTarget, target_merge
from passes.SignalDependencyPass import SignalDependencyPass
from passes.common import PassManager

from pyverilog.vparser.parser import VerilogCodeParser
import pyverilog.utils.util as util

sys.setrecursionlimit(1000000)

parser = argparse.ArgumentParser(description="Translate SystemVerilog to Readable Verilog")
parser.add_argument("--top", dest="top_module", help="top module name")
parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator")
parser.add_argument("-o", dest="output", help="output path")
parser.add_argument("--control", dest="control", default=False, action="store_true",
            help="detect control dependencies")
parser.add_argument("--data", dest="data", default=False, action="store_true",
            help="detect data dependencies")
parser.add_argument("--tag", type=str, help="The verilator tag of instrumented display tasks")
parser.add_argument("--variable", dest="vars", type=str, action="append", default=[], help="the variable of interest. format signal:msb:lsb")
parser.add_argument("--layer", dest="layer", type=int, default=1, help="the number of layers")

args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))

assert(len(args.vars) > 0)
#assert(args.var != None)
#assert(args.idx != None)

#idx = args.idx.split(",")
#msb = int(idx[0])
#lsb = int(idx[1])

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file, skip_opt_veq=True)
ast = v.get_ast()

from model.altsyncram_simple_model import AltsyncramSimpleModel
from model.dcfifo_simple_model import DcfifoSimpleModel
from model.scfifo_simple_model import ScfifoSimpleModel

altsyncram = AltsyncramSimpleModel()
dcfifo = DcfifoSimpleModel()
scfifo = ScfifoSimpleModel()

model_list = [("altsyncram", altsyncram), ("dcfifo", dcfifo), ("scfifo", scfifo)]

pm = PassManager()
pm.register(Logic2RegPass)
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.register(CanonicalFormPass)
pm.register(ArraySplitPass)
pm.runAll(ast)

pm = PassManager()
pm.register(Logic2RegPass)
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.runAll(ast)

tgts = []
for signal in args.vars:
    m = re.findall(r"([0-9a-zA-Z_]+)\:([0-9]+)\:([0-9]+)", signal)
    assert(len(m) == 1 and len(m[0]) == 3)
    name, msb, lsb = m[0]
    tgts.append(TransRecTarget(name, msb=int(msb), lsb=int(lsb)))

for i in range(0, args.layer):
    old_state = pm.state
    pm = PassManager()
    pm.state = old_state

    pm.state.model_list = model_list
    pm.state.top_module = args.top_module

    pm.state.targets = tgts
    pm.register(SignalDependencyPass)
    pm.runAll(ast)

    tgts = []
    if args.control:
        tgts += target_merge(pm.state.control_deps)
    if args.data:
        tgts += target_merge(pm.state.data_deps)
    tgts = target_merge(tgts)

    print("Recorded at layer", i+1)
    for i in tgts:
        print(i.getStr())

old_state = pm.state
pm = PassManager()
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.state = old_state
pm.state.transitionPrintTargets = tgts
pm.register(SimpleRefClockPass)
if args.tag:
    PrintTransitionPass.DISPLAY_TAG = args.tag
pm.register(PrintTransitionPass)
pm.runAll(ast)

codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, "w+") as f:
    f.write(rslt)

