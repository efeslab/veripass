import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getWidth, getConstantWidth
from utils.ValueParsing import verilog_string_to_int

class RefClock:
    def __init__(self, reftype, clock=None, sig=None):
        if clock:
            assert(sig == None)
        elif sig:
            assert(clock == None)
        assert(reftype == "senslist" or reftype == "signal")
        assert(reftype.__class__ == str)
        self.reftype = reftype
        self.clock = clock
        self.sig = sig


"""
This pass identifies the clock with which a signal is referenced.
Only handle simple case where all signals referenced in an assignment
use the same clock.
"""

class SimpleRefClockPass(PassBase):
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, True)
        self.left = None
        self.senslist = None
        self.state.refClockMap = {}
        self.is_left = False

    def visit_Always(self, node):
        sens = []
        for s in node.sens_list.list:
            if "reset" in s.sig.name or "rst" in s.sig.name:
                continue
            sens.append(s)
        self.senslist = vast.SensList(sens)
        self.visit(node.statement)
        self.senslist = None

    def visit_Assign(self, node):
        self.is_left = True
        self.visit(node.left)
        self.is_left = False
        self.visit(node.right)
        self.left = None

    def visit_BlockingSubstitution(self, node):
        self.is_left = True
        self.visit(node.left)
        self.is_left = False
        self.visit(node.right)
        self.left = None

    def visit_NonblockingSubstitution(self, node):
        self.is_left = True
        self.visit(node.left)
        self.is_left = False
        self.visit(node.right)
        self.left = None

    def visit_Identifier(self, node):
        if self.is_left and self.senslist:
            if not node.name in self.state.refClockMap or self.state.refClockMap[node.name].reftype == "signal":
                self.state.refClockMap[node.name] = RefClock("senslist", clock=self.senslist)
        elif self.is_left:
            self.left = node
        elif self.left:
            if not node.name in self.state.refClockMap:
                self.state.refClockMap[node.name] = RefClock("signal", sig=self.left)

def getClockByName(refClockMap, name):
    if not name in refClockMap:
        return None
    r = refClockMap[name]
    while r.reftype == "signal":
        assert(r.sig.name in refClockMap)
        r = refClockMap[r.sig.name]
    return r.senslist
