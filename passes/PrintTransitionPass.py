import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getWidthFromInt, getConstantWidth
from passes.WidthPass import WidthVisitor
from passes.SimpleRefClockPass import getClockByName
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator
from utils.Format import escape_string, beautify_string
import copy

"""
A pass to print out variable value changes.
"""

class TransRecTarget:
    """
    A TransRecTarget tracks a verilog variable whose value changes should be logged via display tasks.
    The variable is defined by argument "ast", a pyverilog ast tree, which has a known width (msb and lsb) and an optional pointer index.
    In brief, the variable should look like name[:ptr]:msb:lsb.
    name is str, representing a verilog identifier.
    msb and lsb have to be integer
    ptr is a vast expression.
    The width (msb and lsb) is mandatory because the need of deduplication.
    """
    # codegen is used to render a TransRecTarget as a string
    codegen = ASTCodeGenerator()
    def __init__(self, name, ptr, msb, lsb, enableData=True, enableControl=True):
        assert(isinstance(name, str) and isinstance(msb, int) and isinstance(lsb, int))
        assert(ptr is None or isinstance(ptr, vast.Node))
        self.name = name
        self.ptr = ptr
        self.msb = msb
        self.lsb = lsb
        self.ast = self.buildAST()
        self.enableData = enableData
        self.enableControl = enableControl

    def getAst(self):
        return self.ast

    def getStr(self):
        aststr = self.codegen.visit(self.ast)
        return aststr

    def getBeautyStr(self):
        # to handle nested, already escaped string
        return beautify_string(self.getStr())

    def getFormatStr(self):
        s = self.getStr()
        return escape_string(s)

    def buildAST(self):
        """
        Build a vast.Node based on the components of a TransRecTarget
        ptr is None or vast.Node
        msb and lsb are integers
        """
        if self.ptr:
            return vast.Partselect(
                    vast.Pointer(vast.Identifier(self.name), self.ptr),
                    vast.IntConst(str(self.msb)),
                    vast.IntConst(str(self.lsb)))
        else:
            return vast.Partselect(
                    vast.Identifier(self.name),
                    vast.IntConst(str(self.msb)),
                    vast.IntConst(str(self.lsb)))

    @classmethod
    def fromStr(cls, s):
        """
        Parse string given from cmdline options to build a TransRecTarget
        Format: name[:ptr]:msb:lsb
        ptr, msb, lsb have to be integers
        """
        fields = s.split(':')
        if len(fields) == 3:
            # name:msb:lsb
            name = fields[0]
            msb = int(fields[1])
            lsb = int(fields[2])
            ptr = None
        elif len(fields) == 4:
            # name:ptr:msb:lsb
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
        existing_shadow_names = set()
        for item in node.items:
            # expect annotation to be "TransRecTarget=xxx"
            if isinstance(item, vast.Variable) and item.annotation is not None:
                if item.annotation.startswith("TransRecTarget"):
                    target_name = item.annotation.split('=')[1]
                    assert(target_name not in existing_targets)
                    existing_targets.add(target_name)
                    existing_shadow_names.add(item.name)
        ldefs = []
        lalways = {}
        for target in self.state.transitionPrintTargets:
            # skip if there is no ref clock
            sens = getClockByName(self.state.refClockMap, target.name)
            if sens is None:
                print("Warning, skipping transition target {} due to no ref clock".format(target.getStr()))
                continue
            if not sens in lalways:
                lalways[sens] = vast.Always(sens, vast.Block([]))

            # skip if the transition target is duplicated
            target_name = target.getFormatStr()
            if target_name in existing_targets:
                print("Warning, skipping already recorded transition target {}".format(target.getStr()))
                continue
            existing_targets.add(target_name)
            # find a name for the "shadow" signal (delayed by one cycle to detect changes)
            target_name_delayed = target_name + "__Q__"
            if len(target_name_delayed) > 128:
                # if the target_name (escaped string) is too long, use the hash instead.
                # note that the hash collision is not handled
                # note that the hash value could be negative, so we still need to escape
                target_name_delayed = escape_string("TransRecTarget_{:X}__Q__".format(hash(target_name)))
                assert(target_name_delayed not in existing_shadow_names)
                existing_shadow_names.add(target_name_delayed)
            target_ast = target.getAst()
            target_width = getWidthFromInt(self.widthVisitor.getWidth(target_ast))

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
                        vast.StringConst("[%0t] {} updated to %h".format(target.getBeautyStr())),
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
