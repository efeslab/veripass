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
from passes.InsertCountingPass import InsertCountingPass, ValidBitTarget
from passes.common import PassManager

from pyverilog.vparser.parser import VerilogCodeParser
import pyverilog.utils.util as util

parser = argparse.ArgumentParser(description="Translate SystemVerilog to Readable Verilog")
parser.add_argument("--top", dest="top_module", help="top module name")
parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator")
parser.add_argument("-o", dest="output", help="output path")
parser.add_argument("--reset", dest="reset", help="specify the reset signal")
parser.add_argument("--valid-signals", dest="signals", help="specify the valid signals to count")
parser.add_argument("--counter-width", type=int, dest="counter_width", default=32, help="the width of counters")

args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))
print("Counter Width: {}".format(args.counter_width))
print("Reset Signal: {}".format(args.reset))

validbits = []
signals = args.signals.split(",")
for signal in signals:
    if not "-" in signal:
        validbits.append(ValidBitTarget(signal))
    elif not ":" in signal:
        s = signal.split("-")
        name = s[0]
        s = s[1]
        validbits.append(ValidBitTarget(name, ptr=int(s)))
    else:
        s = signal.split("-")
        if len(s) == 2:
            name = s[0]
            s = s[1]
            s = s.split(":")
            msb = int(s[0])
            lsb = int(s[1])
            assert(msb == lsb)
            validbits.append(ValidBitTarget(name, index=lsb))
        else:
            assert(len(s) == 3)
            name = s[0]
            ptr = int(s[1])
            s = s[2]
            s = s.split(":")
            msb = int(s[0])
            lsb = int(s[1])
            assert(msb == lsb)
            validbits.append(ValidBitTarget(name, ptr=ptr, index=lsb))

print("Signals:")
for v in validbits:
    print(v.getStr())

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file, skip_opt_veq=True)
ast = v.get_ast()

from model.altsyncram_simple_model import AltsyncramSimpleModel
from model.dcfifo_simple_model import DcfifoSimpleModel
from model.scfifo_simple_model import ScfifoSimpleModel

altsyncram = AltsyncramSimpleModel()
dcfifo = DcfifoSimpleModel()
scfifo = ScfifoSimpleModel()

pm = PassManager()
pm.register(Logic2RegPass)
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.register(CanonicalFormPass)
pm.register(ArraySplitPass)
pm.runAll(ast)

pm = PassManager()
pm.state.variablesToCount = validbits
pm.state.counterWidth = args.counter_width
pm.state.reset = args.reset
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.register(SimpleRefClockPass)
pm.register(InsertCountingPass)
pm.runAll(ast)

#print(pm.state.generatedSignalsTransRecTarget)
trans = pm.state.generatedSignalsTransRecTarget

pm = PassManager()
pm.register(IdentifierRefPass)
pm.register(TypeInfoPass)
pm.register(WidthPass)
pm.runAll(ast)

old_state = pm.state
pm = PassManager()
pm.state = old_state
pm.state.transitionPrintTargets = trans
pm.register(SimpleRefClockPass)
pm.register(PrintTransitionPass)
pm.runAll(ast)

codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, "w+") as f:
    f.write(rslt)

