#!/usr/bin/env python3
import os
import sys
import pathlib
import argparse
import time
import re
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

from model.altsyncram_simple_model import AltsyncramSimpleModel
from model.dcfifo_simple_model import DcfifoSimpleModel
from model.scfifo_simple_model import ScfifoSimpleModel

def deps_regParser(subparsers):
    p = subparsers.add_parser('deps', help="Instrument display for given variables and its control/data dependencies") 
    p.set_defaults(toolEntry=deps_entry)
    p.add_argument("--control", dest="control", default=False, action="store_true",
        help="detect control dependencies")
    p.add_argument("--data", dest="data", default=False, action="store_true",
        help="detect data dependencies")
    p.add_argument("--tag", type=str, help="The verilator tag of instrumented display tasks")
    p.add_argument("--variable", dest="vars", type=str, action="append", default=[], help="the variable of interest. Format is signal[:ptr]:msb:lsb. (can be stacked)")
    p.add_argument("--layer", dest="layer", type=int, default=1, help="the number of layers")

def deps_entry(args, ast):
    sys.setrecursionlimit(1000000)
    assert(len(args.vars) > 0)
    #assert(args.var != None)
    #assert(args.idx != None)

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
        tgts.append(TransRecTarget.fromStr(signal))

    tgts_list = tgts
    print("Recorded at layer 0")
    for i in tgts:
        print(i.getStr())
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
        tgts_list += tgts
        tgts_list = target_merge(tgts_list)

    old_state = pm.state
    pm = PassManager()
    pm.register(IdentifierRefPass)
    pm.register(TypeInfoPass)
    pm.register(WidthPass)
    pm.state = old_state
    pm.state.transitionPrintTargets = tgts_list
    pm.register(SimpleRefClockPass)
    if args.tag:
        PrintTransitionPass.DISPLAY_TAG = args.tag
    pm.register(PrintTransitionPass)
    pm.runAll(ast)
