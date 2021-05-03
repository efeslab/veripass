#!/usr/bin/env python3
import argparse
import shlex
import copy
import json
from verilator import Verilator
from verilator import ASTCodeGenerator
from dbgtools.sv2v import sv2v_regParser
from dbgtools.fsm_detect import fsm_detect_regParser
from dbgtools.deps import deps_regParser
from dbgtools.autocnt import autocnt_regParser
from passes.common import PassManager
from passes.VerilatorReTagPass import VerilatorReTagPass
from jinja2 import Environment, FileSystemLoader

def output_regParser(subparsers):
    """
    output an ast to a file
    """
    p = subparsers.add_parser('output', help="Output the ast processed so far to a file")
    p.add_argument("--not-retag-synthesis", action="store_true", help="Do not retag \"synthesis\" metacommands. Should be used to generate synthesizable code. (default=False)")
    p.set_defaults(toolEntry=output_entry)
    p.add_argument("-o", dest="output", type=str, help="output path")

def output_entry(args, ast):
    # make a copy of the ast so that an intermediate "output" will not pollute the annotations and affect later passes
    # this is helpful if the ouput is not the last command
    ast_copy = copy.deepcopy(ast)
    pm = PassManager()
    if args.not_retag_synthesis:
        VerilatorReTagPass.SYNTHESIS_RETAG = False
    pm.register(VerilatorReTagPass)
    pm.runAll(ast_copy)
    codegen = ASTCodeGenerator()
    rslt = codegen.visit(ast_copy)
    with open(args.output, 'w+') as f:
        f.write(rslt)

    if hasattr(ast, "condname2display"):
        with open(args.output+".displayinfo.txt", 'w+') as f:
            for condname in ast.condname2display:
                f.write("{} {}\n".format(condname, ast.condname2display[condname]))
    if hasattr(ast, "displayarg_width"):
        with open(args.output+".widthinfo.txt", 'w+') as f:
            for varname in ast.displayarg_width:
                f.write("{} {}\n".format(varname, ast.displayarg_width[varname]))

parser = argparse.ArgumentParser(description="A collection of tools for FPGA debugging")
parser.add_argument("--top", dest="top_module", help="top module name")
input_parser = parser.add_mutually_exclusive_group(required=False)
input_parser.add_argument("-F", dest="desc_file", type=str, help="description file path, similar to verilator. Cannot coexist with -f.")
input_parser.add_argument("-f", dest="files", type=str, action="append", help="single input file path. Cannot coexist with -F.")
# you either use the output command in a config file or specify the output file
output_parser = parser.add_mutually_exclusive_group(required=False)
output_parser.add_argument("--config", type=str, help="A config file, one tool subcommand per line.")
output_parser.add_argument("-o", dest="output", help="output path")
parser.add_argument("--config-override", type=str, default="{}", help="A json string which can override the given config")
parser.add_argument("--reset", default=None, type=str, help="Specify the reset identifier (e.g. RESET or !RESETN)")
parser.add_argument("--recording-emulated", default=False, action="store_true", help="Use the emulated data recording implementation. (default=False)")
parser.add_argument("--not-retag-synthesis", action="store_true", help="Do not retag \"synthesis\" metacommands. Should be used to generate synthesizable code. (default=False)")
subparsers = parser.add_subparsers(title="Available FPGA debugging tools")
sv2v_regParser(subparsers)
fsm_detect_regParser(subparsers)
deps_regParser(subparsers)
autocnt_regParser(subparsers)
output_regParser(subparsers)
args = parser.parse_args()
print("Top Module: {}".format(args.top_module))
print("Desc File: {}".format(args.desc_file))
print("Output Path: {}".format(args.output))

v = Verilator(top_module_name=args.top_module, desc_file=args.desc_file, files=args.files)
ast = v.get_ast()

if args.config:
    config_override = json.loads(args.config_override)
    env = Environment(loader=FileSystemLoader('./'))
    template = env.get_template(args.config)
    content = template.render(config_override)
    content = content.replace('\\\n', '')
    for cmdline in content.splitlines():
        if len(cmdline) == 0 or cmdline[0] == '#':
            continue
        conf_args = copy.deepcopy(args)
        parser.parse_args(shlex.split(cmdline), namespace=conf_args)
        conf_args.toolEntry(conf_args, ast)
else:
    args.toolEntry(args, ast)
    output_entry(args, ast)
