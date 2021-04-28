import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getWidthFromInt, getConstantWidth
from passes.WidthPass import WidthVisitor
from passes.SimpleRefClockPass import getClockByName
from utils.Format import format_name, beautify_name
import copy

"""
A pass to print out variable value changes.
"""

class TransRecTarget:
    """
    A TransRecTarget tracks a verilog variable whose value changes should be logged via display tasks.
    The variable must have a known width (msb and lsb) but can have an optional pointer index.
    """
    def __init__(self, name, ptr, msb, lsb, enableData=True, enableControl=True):
        assert(msb is not None and lsb is not None)
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
        return beautify_name(s)

    def getFormatStr(self):
        s = self.getStr()
        s = format_name(s)
        return s

    @classmethod
    def fromStr(cls, s):
        """
        Parse string given from cmdline options to build a TransRecTarget
        Format: name[:ptr]:msb:lsb
        """
        fields = s.split(':')
        if len(fields) == 3:
            name = fields[0]
            msb = int(fields[1])
            lsb = int(fields[2])
            ptr = None
        elif len(fields) == 4:
            name = fields[0]
            ptr = int(fields[1])
            msb = int(fields[2])
            lsb = int(fields[3])
        else:
            raise NotImplementedError("Cannot recognize the format")
        return TransRecTarget(name, ptr, msb, lsb)

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

    def visit_ModuleDef(self, node):
        existing_targets = set()
        for item in node.items:
            # expect annotation to be "TransRecTarget=xxx"
            if isinstance(item, vast.Variable) and item.annotation is not None:
                if item.annotation.startswith("TransRecTarget"):
                    target_name = item.annotation.split('=')[1]
                    assert(target_name not in existing_targets)
                    existing_targets.add(target_name)
        ldefs = []
        lalways = {}
        for target in self.state.transitionPrintTargets:
            target_name = target.getFormatStr()
            target_name_delayed = target_name + "__Q__"
            target_ast = target.getAst()
            target_width = getWidthFromInt(self.widthVisitor.getWidth(target_ast))

            sens = getClockByName(self.state.refClockMap, target.name)
            if sens is None:
                print("Warning, skipping transition target {} due to no ref clock".format(target.getStr()))
                continue
            if target_name in existing_targets:
                print("Warning, skipping already recorded transition target {}".format(target.getStr()))
                continue
            if not sens in lalways:
                lalways[sens] = vast.Always(sens, vast.Block([]))

            def_annotation = "TransRecTarget={}".format(target_name)
            ldefs.append(vast.Logic(target_name_delayed, target_width, annotation=def_annotation))
            lalways[sens].statement.statements.append(
                    vast.NonblockingSubstitution(
                        vast.Identifier(target_name_delayed),
                        target_ast))
            lalways[sens].statement.statements.append(
                vast.IfStatement(
                    vast.NotEq(target_ast, vast.Identifier(target_name_delayed)),
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
