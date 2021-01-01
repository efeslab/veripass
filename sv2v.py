import os
import sys
import pathlib
import argparse
from verilator import *

parser = argparse.ArgumentParser(description="Translate SystemVerilog to Readable Verilog")
parser.add_argument("--top", dest="top_module", help="top module name")
parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator")
parser.add_argument("-o", dest="output", help="output path")

args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file)
ast = v.get_ast()
codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, 'w+') as f:
    f.write(rslt)
