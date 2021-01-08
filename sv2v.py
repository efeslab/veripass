import os
import sys
import pathlib
import argparse
from verilator import *

parser = argparse.ArgumentParser(description="Translate SystemVerilog to Readable Verilog")
parser.add_argument("--top", dest="top_module", help="top module name")
parser.add_argument("-F", dest="desc_file", help="description file path, similar to verilator")
parser.add_argument("-o", dest="output", help="output path")
parser.add_argument("--split", default=False, action="store_true", dest="split", help="whether to split variable")

args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))
print("Split Variables: {}".format(args.split))

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file)
if args.split:
    ast = v.get_splitted_ast()
else:
    ast = v.get_ast()
codegen = ASTCodeGenerator()
rslt = codegen.visit(ast)
with open(args.output, 'w+') as f:
    f.write(rslt)

#used_vars = v.get_used_vars()
#typetable = v.get_typetable()
#total = 0
#dff = 0
#nodff = 0
#unknown = 0
#for name in used_vars:
#    varref = used_vars[name]
#    varref_dtype = typetable[varref.dtype_id]
#    if varref_dtype.array_len == 0:
#        for i in range(0, varref_dtype.width):
#            total += 1
#            if varref.dff[i] == True:
#                dff += 1
#            elif varref.dff[i] == False:
#                nodff += 1
#            elif varref.dff[i] == None:
#                unknown += 1
#    else:
#        for i in range(0, varref_dtype.array_len):
#            for j in range(0, varref_dtype.width):
#                total += 1
#                if varref.dff[i][j] == True:
#                    dff += 1
#                elif varref.dff[i][j] == False:
#                    nodff += 1
#                elif varref.dff[i][j] == None:
#                    unknown += 1
#print(total, dff, nodff, unknown)
#
#
