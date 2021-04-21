import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getWidthFromInt, getConstantWidth
from passes.WidthPass import WidthVisitor
from utils.Format import format_name
import copy

"""
A pass to print out variable value changes.
"""

class TransRecTarget:
    def __init__(self, name, ptr=None, msb=None, lsb=None, enableData=True, enableControl=True):
        self.name = name
        self.ptr = ptr
        self.msb = msb
        self.lsb = lsb
        self.enableData = enableData
        self.enableControl = enableControl

        if msb != None:
            assert(lsb != None)

    def isArray(self):
        return self.ptr != None

    def isSelect(self):
        return self.lsb != None

    def getAst(self):
        if not self.isArray() and not self.isSelect():
            return vast.Identifier(self.name)
        elif not self.isArray() and self.isSelect():
            return vast.Partselect(vast.Identifier(self.name),
                    vast.IntConst(str(self.msb)),
                    vast.IntConst(str(self.lsb)))
        elif self.isArray() and not self.isSelect():
            return vast.Pointer(vast.Identifier(self.name),
                    vast.IntConst(str(self.ptr)))
        elif self.isArray() and self.isSelect():
            return vast.Partselect(
                    vast.Pointer(
                        vast.Identifier(self.name),
                        vast.IntConst(str(self.ptr))),
                    vast.IntConst(str(self.msb)),
                    vast.IntConst(str(self.lsb)))

    def getStr(self):
        s = self.name
        if self.ptr != None:
            s += ("[" + str(self.ptr) + "]")
        if self.msb != None:
            s += ("[" + str(self.msb) + ":" + str(self.lsb) + "]")
        return s

    def getFormatStr(self):
        s = self.getStr()
        s = format_name(s)
        return s

def target_merge(targets):
    targets = copy.deepcopy(targets)
    changed = True
    while changed:
        changed = False
        new_targets = []
        for target in targets:
            need_insert = True
            for i in range(0, len(new_targets)):
                if new_targets[i].name != target.name:
                    continue
                if target.msb >= new_targets[i].lsb - 1 and target.lsb <= new_targets[i].msb + 1:
                    new_msb = target.msb if target.msb > new_targets[i].msb else new_targets[i].msb
                    new_lsb = target.lsb if target.lsb < new_targets[i].lsb else new_targets[i].lsb
                    new_targets[i].msb = new_msb
                    new_targets[i].lsb = new_lsb
                    need_insert = False
                    break
            if need_insert:
                new_targets.append(target)
        if targets != new_targets:
            changed = True
        targets = new_targets
    return new_targets

class PrintTransitionPass(PassBase):
    """
    Configurations:
    1. DISPLAY_TAG: the verilator tag attachted to insturmented display tasks
    """
    DISPLAY_TAG = "debug_display"
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, False)
        self.widthVisitor = WidthVisitor(pass_state)
        assert(hasattr(self.state, "transitionPrintTargets"))
        assert(hasattr(self.state, "refClockMap"))
        #assert(hasattr(self.state, "enableData"))
        #assert(hasattr(self.state, "enableControl"))
        self.if_stack = []

    def getRefClock(self, target):
        name = target.name
        if name not in self.state.refClockMap:
            return None
        else:
            ref = self.state.refClockMap[name]
        while ref.reftype == "signal":
            name = ref.sig.name
            ref = self.state.refClockMap[name]
        return ref.clock

    def visit_ModuleDef(self, node):
        ldefs = []
        lalways = {}

        for target in self.state.transitionPrintTargets:
            target_ast = target.getAst()
            target_width = getWidthFromInt(self.widthVisitor.getWidth(target_ast))
            sens = self.getRefClock(target)
            if sens is None:
                print("Warning, skipping transition target {} due to no ref clock".format(target.getStr()))
                continue
            if not sens in lalways:
                lalways[sens] = vast.Always(sens, vast.Block([]))

            ldefs.append(vast.Logic(target.getFormatStr()+"__Q__", target_width))
            lalways[sens].statement.statements.append(
                    vast.NonblockingSubstitution(
                        vast.Identifier(target.getFormatStr()+"__Q__"),
                        target.getAst()))
            lalways[sens].statement.statements.append(
                vast.IfStatement(
                    vast.NotEq(
                        vast.Identifier(target.name), vast.Identifier(target.name+"__Q__")),
                    vast.SingleStatement(vast.SystemCall("display", [
                        vast.StringConst("[%0t] {} updated to %h".format(target.getStr())),
                        vast.SystemCall("time", []),
                        target.getAst()],
                        anno=self.DISPLAY_TAG
                    )),
                    None
                )
            )

        node.items += ldefs
        for s in lalways:
            node.items.append(lalways[s])
