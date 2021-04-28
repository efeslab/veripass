#!/usr/bin/env python3
import argparse
from verilator import Verilator
from verilator import ASTCodeGenerator
from dbgtools.sv2v import sv2v_regParser
from dbgtools.fsm_detect import fsm_detect_regParser
from dbgtools.deps import deps_regParser
from dbgtools.autocnt import autocnt_regParser
from passes.common import PassManager
from passes.VerilatorReTagPass import VerilatorReTagPass

parser = argparse.ArgumentParser(description="A collection of tools for FPGA debugging")
parser.add_argument("--top", dest="top_module", help="top module name")
input_parser = parser.add_mutually_exclusive_group()
input_parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator. Cannot coexist with -f.")
input_parser.add_argument("-f", dest="files", type=str, action="append", help="single input file path. Cannot coexist with -F.")
parser.add_argument("-o", dest="output", help="output path")
parser.add_argument("--reset", default=None, type=str, help="Specify the reset identifier (e.g. RESET or !RESETN)")
parser.add_argument("--not-retag-synthesis", action="store_true", help="Do not retag \"synthesis\" metacommands. Should be used to generate synthesizable code. (default=False)")
subparsers = parser.add_subparsers(title="Available FPGA debugging tools")
sv2v_regParser(subparsers)
fsm_detect_regParser(subparsers)
deps_regParser(subparsers)
autocnt_regParser(subparsers)
args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file, files=args.files)
ast = v.get_ast()

args.toolEntry(args, ast)

pm = PassManager()
if args.not_retag_synthesis:
    VerilatorReTagPass.SYNTHESIS_RETAG = False
pm.register(VerilatorReTagPass)
pm.runAll(ast)

codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, 'w+') as f:
    f.write(rslt)