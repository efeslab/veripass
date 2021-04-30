import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getDimensions, getConstantWidth, getWidthFromInt, getWidth
from passes.PrintTransitionPass import TransRecTarget
from utils.Format import escape_string

class ValidBitTarget:
    def __init__(self, name, ptr=None, index=None):
        self.name = name
        self.ptr = ptr
        self.index = index

    def getAst(self):
        if self.ptr == None and self.index == None:
            return vast.Identifier(self.name)
        elif self.ptr == None and self.index != None:
            return vast.Partselect(
                    vast.Identifier(self.name),
                    vast.IntConst(str(self.index)),
                    vast.IntConst(str(self.index)))
        elif self.ptr != None and self.index == None:
            return vast.Pointer(
                    vast.Identifier(self.name),
                    vast.IntConst(str(self.ptr)))
        elif self.ptr != None and self.index != None:
            return vast.Partselect(
                    vast.Pointer(vast.Identifier(self.name), vast.IntConst(str(self.ptr))),
                    vast.IntConst(str(self.index)),
                    vast.IntConst(str(self.index)))

    def getStr(self):
        s = self.name
        if self.ptr != None:
            s += ("[" + str(self.ptr) + "]")
        if self.index != None:
            s += ("[" + str(self.index) + ":" + str(self.index) + "]")
        return s

    def getFormatStr(self):
        s = self.getStr()
        s = escape_string(s)
        return s

    @classmethod
    def fromStr(cls, s):
        """
        Parse string given from cmdline options to build a TransRecTarget
        Format: name[:ptr]:index
        """
        fields = s.split(':')
        if len(fields) == 2:
            name = fields[0]
            index = int(fields[1])
            ptr = None
        elif len(fields) == 3:
            name = fields[0]
            ptr = int(fields[1])
            index = int(fields[2])
        else:
            raise NotImplementedError("Cannot recognize the format")
        return ValidBitTarget(name, ptr, index)


"""
A pass to add counting logic for specified variables.
"""

class InsertCountingPass(PassBase):
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, False)
        assert(hasattr(self.state, "identifierRef"))
        assert(hasattr(self.state, "variablesToCount"))
        assert(hasattr(self.state, "counterWidth"))
        assert(hasattr(self.state, "reset"))

        assert(self.state.reset.name in self.state.identifierRef)
        for v in self.state.variablesToCount:
            assert(v.name in self.state.identifierRef)

        self.state.generatedSignalsTransRecTarget = []

    def get_counter_name(self, var):
        return var.getFormatStr() + "__COUNT__"

    def get_counter_def(self, var):
        return vast.Logic(self.get_counter_name(var), getWidthFromInt(self.state.counterWidth))

    def get_counter_ref(self, var):
        return vast.Identifier(self.get_counter_name(var))

    def get_ref_clock(self, var):
        name = var.name
        ref = self.state.refClockMap[name]
        while ref.reftype == "signal":
            name = ref.sig.name
            ref = self.state.refClockMap[name]
        return ref.clock

    def visit_ModuleDef(self, node):
        ldefs = []
        lalways = {}

        for var in self.state.variablesToCount:
            sens = self.get_ref_clock(var)
            ldefs.append(self.get_counter_def(var))

            self.state.generatedSignalsTransRecTarget.append(
                TransRecTarget.fromStr("{name}:{msb}:{lsb}".format(
                    name=self.get_counter_name(var), msb=self.state.counterWidth - 1, lsb=0)))

            if not sens in lalways:
                lalways[sens] = vast.Always(sens, vast.Block([]))

            lalways[sens].statement.statements.append(
                    vast.IfStatement(
                        self.state.reset,
                        vast.NonblockingSubstitution(
                            self.get_counter_ref(var),
                            vast.IntConst(str(self.state.counterWidth)+"'h0")),
                        vast.IfStatement(
                            var.getAst(),
                            vast.NonblockingSubstitution(
                                self.get_counter_ref(var),
                                vast.Plus(
                                    vast.IntConst(str(self.state.counterWidth)+"'h1"),
                                    self.get_counter_ref(var)
                                )
                            ),
                            None)
                        )
                    )

        node.items += ldefs
        for s in lalways:
            node.items.append(lalways[s])


