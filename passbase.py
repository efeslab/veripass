import sys
import os
import math
import tempfile
import pathlib
import verilator
import copy
import pyverilog.vparser.ast as vast

def verilog_string_to_int(s):
    value_pos = s.find("h")
    if value_pos >= 0:
        return int("0x"+s[value_pos+1:], 16)
    else:
        value_pos = s.find("b")
        if value_pos >= 0:
            return int("0b"+s[value_pos+1:], 16)
        else:
            value_pos = s.find("'")
            assert(value_pos == -1)
            return int(s)

class BaseVisitor(object):
    def __init__(self):
        self.stack = []

    def visit(self, node):
        self.stack.append((node.__class__, node))
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        r = visitor(node)
        self.stack.pop()
        return r

    def generic_visit(self, node):
        ret = []
        for c in node.children():
            ret += self.visit(c)
        return ret

    def visit_str(self, node):
        return []

