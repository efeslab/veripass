#!/usr/bin/env python3
import os
import sys
import pathlib
import time
from passes.IdentifierRefPass import IdentifierRefPass
from passes.TypeInfoPass import TypeInfoPass
from passes.WidthPass import WidthPass
from passes.CanonicalFormPass import CanonicalFormPass
from passes.TaskSupportPass import TaskSupportPass
from passes.ArraySplitPass import ArraySplitPass
from passes.Logic2RegPass import Logic2RegPass
from passes.BoundaryCheckPass import ArrayBoundaryCheckPass
from passes.common import PassManager

from pyverilog.vparser.parser import VerilogCodeParser
import pyverilog.utils.util as util


def sv2v_regParser(subparsers):
    """
    subparsers is the return value of "add_subparsers"
    """
    p = subparsers.add_parser('sv2v', help="Translate modulized SystemVerilog to a monolithic, synthesizable (System)Verilog")
    p.set_defaults(toolEntry=sv2v_entry)
    p.add_argument("--split", default=False, action="store_true", dest="split", help="whether to split variable")
    p.add_argument("--tasksupport", default=False, action="store_true", help="whether to run TaskSupportPass")
    p.add_argument("--tasksupport-mode", default='STP', choices=['STP', 'SWEEP', 'ILA'], help="in what mode to run TaskSupportPass (default is STP)")
    p.add_argument("--tasksupport-tags", type=str, default=[], action="append", help="The tag (e.g. debug_display) enabling instrumentations of specific display tasks")
    p.add_argument("--tasksupport-log2width", default=0, type=int, help="The log2(width) of the fake data to instrument recording for")
    p.add_argument("--tasksupport-log2depth", default=0, type=int, help="The log2(depth) of the fake data to instrument recording for")
    p.add_argument("--arrayboundcheck", action="store_true", help="Instrument array bound checking.")

def sv2v_entry(args, ast):
    print("Split Variables: {}".format(args.split))

    pm = PassManager()
    if args.reset:
        pm.state.set_reset(args.reset)
    #pm.register(Logic2RegPass)
    pm.register(IdentifierRefPass)
    pm.register(TypeInfoPass)
    pm.register(WidthPass)
    pm.register(CanonicalFormPass)
    if args.arrayboundcheck:
        pm.register(ArrayBoundaryCheckPass)
    if args.tasksupport:
        if args.tasksupport_mode == "SWEEP":
            TaskSupportPass.INSTRUMENT_TYPE = TaskSupportPass.INSTRUMENT_TYPE_SWEEP
            TaskSupportPass.INSTRUMENT_SWEEP_CFG_WIDTH = 2**args.tasksupport_log2width
            TaskSupportPass.INSTRUMENT_SWEEP_CFG_DEPTH = 2**args.tasksupport_log2depth
        elif args.tasksupport_mode == "STP":
            TaskSupportPass.INSTRUMENT_TYPE = TaskSupportPass.INSTRUMENT_TYPE_INTELSTP
        elif args.tasksupport_mode == "ILA":
            TaskSupportPass.INSTRUMENT_TYPE = TaskSupportPass.INSTRUMENT_TYPE_XILINXILA
        else:
            raise NotImplementedError("Unknown TaskSupport Mode")
        # If INSTURMENT_TAGS is empty, instrument all display tasks.
        TaskSupportPass.INSTRUMENT_TAGS = set(args.tasksupport_tags)
        # If not empty, only instrument ones with the given verilator tags. This should also include the display instrumented above.
        if len(TaskSupportPass.INSTRUMENT_TAGS) > 0:
            TaskSupportPass.INSTRUMENT_TAGS.add(ArrayBoundaryCheckPass.DISPLAY_TAG)
        pm.register(TaskSupportPass)
    #pm.register(ArraySplitPass)
    pm.runAll(ast)

    #for name in pm.state.array_access_info:
    #    print(name, pm.state.array_access_info[name])
