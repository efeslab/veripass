#!/usr/bin/env python3
import argparse
from jinja2 import Environment, FileSystemLoader
import json

parser = argparse.ArgumentParser(
    description="Generate Vivado tcl scripts for synthesis")
parser.add_argument("-T", "--template", dest="template",
                    type=str, required=True, help="Path to the tcl template")
parser.add_argument("--projpath", type=str, default=".", help="(default is .)")
parser.add_argument("--projname", type=str, required=True, help="(required)")
parser.add_argument("--source", dest="sources", type=str, required=True, action="append", help="(required) All source code need to be imported in vivado")
parser.add_argument("--svsrc", dest="svsrcs", type=str, required=True, action="append", help="(required) Systemverilog source code")
parser.add_argument("--top", type=str, required=True, help="(required) Top-Level Module name")
parser.add_argument("--ila", type=str, default='', help="(optional) path to the ila.tcl")
parser.add_argument("-o", dest="output", type=str, required=True,
                    help="(required) Path to the output rendered tcl scripts")
args = parser.parse_args()
env = Environment(loader=FileSystemLoader('./'))
template = env.get_template(args.template)
config = {
    "PROJNAME": args.projname,
    "PROJPATH": args.projpath,
    "SOURCES": ' '.join(args.sources),
    "SV_SRCS": args.svsrcs,
    "TOP_MODULE": args.top,
    "ILA_TCL": args.ila, # '' means no needed, should be handled by template
}
rslt = template.render(config)
with open(args.output, "w") as f:
    f.write(rslt)
