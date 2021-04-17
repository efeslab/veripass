#!/usr/bin/env python3
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
from passes.ArraySplitPass import ArraySplitPass
from passes.Logic2RegPass import Logic2RegPass
from passes.SimpleRefClockPass import SimpleRefClockPass
from passes.BoundaryCheckPass import ArrayBoundaryCheckPass
from passes.StateMachineDetectionPass import StateMachineDetectionPass
from passes.PrintTransitionPass import PrintTransitionPass, TransRecTarget
from passes.common import PassManager

from pyverilog.vparser.parser import VerilogCodeParser
import pyverilog.utils.util as util

parser = argparse.ArgumentParser(description="Translate SystemVerilog to Readable Verilog")
parser.add_argument("--top", dest="top_module", help="top module name")
parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator")
parser.add_argument("-o", dest="output", help="output path")

args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))

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

# enable state machine detection
pm.state.model_list = model_list
pm.state.top_module = args.top_module
pm.register(StateMachineDetectionPass)
pm.runAll(ast)

old_state = pm.state

tgts = set()
for i in pm.state.fsm:
    tgts.add(TransRecTarget(i.name))
    print(i.name)

pm = PassManager()
pm.state = old_state
pm.state.transitionPrintTargets = tgts
pm.register(SimpleRefClockPass)
pm.register(PrintTransitionPass)
pm.runAll(ast)

codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, "w+") as f:
    f.write(rslt)

