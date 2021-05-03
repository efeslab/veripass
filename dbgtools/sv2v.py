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
from passes.BoundaryCheckPass import ArrayBoundaryCheckPass
from passes.common import PassManager
from utils.XilinxILA import XilinxILA

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
    p.add_argument("--tasksupport-mode", default='STP', choices=['STP', 'SWEEPSTP', 'SWEEPILA', 'ILA'], help="in what mode to run TaskSupportPass (default is STP)")
    p.add_argument("--tasksupport-tags", type=str, default=[], action="append", help="The tag (e.g. debug_display) enabling instrumentations of specific display tasks")
    p.add_argument("--tasksupport-log2width", default=None, type=int, help="The log2(width) of the fake data to instrument recording for")
    p.add_argument("--tasksupport-log2depth", default=None, type=int, help="The log2(depth) of the fake data to instrument recording for")
    p.add_argument("--tasksupport-ila-tcl", type=str, help="The path of the generated ila tcl scripts, which configs the ila IP with proper properties.")
    p.add_argument("--arrayboundcheck", action="store_true", help="Instrument array bound checking.")

def sv2v_entry(args, ast):
    print("Split Variables: {}".format(args.split))

    pm = PassManager()
    if args.reset:
        pm.state.set_reset(args.reset)
    pm.register(IdentifierRefPass)
    pm.register(TypeInfoPass)
    pm.register(WidthPass)
    pm.register(CanonicalFormPass)
    if args.arrayboundcheck:
        pm.register(ArrayBoundaryCheckPass)
    if args.tasksupport:
        if args.recording_emulated:
            TaskSupportPass.RECORDING_EMULATED = True
        if args.tasksupport_mode == "SWEEPSTP":
            TaskSupportPass.INSTRUMENT_TYPE = TaskSupportPass.INSTRUMENT_TYPE_SWEEPSTP
            TaskSupportPass.INSTRUMENT_SWEEP_CFG_WIDTH = 2**args.tasksupport_log2width
            TaskSupportPass.INSTRUMENT_SWEEP_CFG_DEPTH = 2**args.tasksupport_log2depth
        elif args.tasksupport_mode == 'SWEEPILA':
            TaskSupportPass.INSTRUMENT_TYPE = TaskSupportPass.INSTRUMENT_TYPE_SWEEPILA
            TaskSupportPass.INSTRUMENT_SWEEP_CFG_WIDTH = 2**args.tasksupport_log2width
            TaskSupportPass.INSTRUMENT_SWEEP_CFG_DEPTH = 2**args.tasksupport_log2depth
        elif args.tasksupport_mode == "STP":
            TaskSupportPass.INSTRUMENT_TYPE = TaskSupportPass.INSTRUMENT_TYPE_INTELSTP
            if args.tasksupport_log2depth:
                TaskSupportPass.INSTRUMENT_SAMPLE_DEPTH = 2**args.tasksupport_log2depth
        elif args.tasksupport_mode == "ILA":
            TaskSupportPass.INSTRUMENT_TYPE = TaskSupportPass.INSTRUMENT_TYPE_XILINXILA
            if args.tasksupport_log2depth:
                TaskSupportPass.INSTRUMENT_SAMPLE_DEPTH = 2**args.tasksupport_log2depth
        else:
            raise NotImplementedError("Unknown TaskSupport Mode")
        if args.tasksupport_ila_tcl:
            XilinxILA.ILA_TCL_OUTPUT = args.tasksupport_ila_tcl
        # If INSTURMENT_TAGS is empty, instrument all display tasks.
        TaskSupportPass.INSTRUMENT_TAGS = set(args.tasksupport_tags)
        # If not empty, only instrument ones with the given verilator tags. This should also include the display instrumented above.
        if len(TaskSupportPass.INSTRUMENT_TAGS) > 0:
            TaskSupportPass.INSTRUMENT_TAGS.add(ArrayBoundaryCheckPass.DISPLAY_TAG)
        pm.register(TaskSupportPass)
    pm.runAll(ast)

    # An ugly hack that passes information across stages...
    # since ast is the only thing that should be passed
    if len(pm.state.condname2display) != 0:
        ast.condname2display = pm.state.condname2display
    if len(pm.state.displayarg_width) != 0:
        ast.displayarg_width = pm.state.displayarg_width
