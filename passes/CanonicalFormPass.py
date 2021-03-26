import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getWidthFromInt


class CanonicalFormPass(PassBase):
    """
    Will use the width info from pass_state
    """

    def __init__(self, pass_state):
        # Fallback to visit_children
        super().__init__(pass_state, True)
        self.widthtbl = self.state.widthtbl
    """
    Do not return anything. All code transformation is inline
    """

    def visit_ModuleDef(self, node):
        # type: (vast.Identifier, vast.Node)
        self.promoted_wires = []
        self.visit_children(node)
        instrumented_statements = []
        for identifier, val in self.promoted_wires:
            new_width = self.widthtbl[val]
            new_wire = vast.Wire(identifier.name, getWidthFromInt(new_width))
            new_assign = vast.Assign(identifier, val)
            instrumented_statements.append(new_wire)
            instrumented_statements.append(new_assign)
        node.items = instrumented_statements + node.items

    def visit_Partselect(self, node):
        self.visit_children(node)
        if not isinstance(node.var, vast.Identifier) and not isinstance(node.var, vast.Pointer):
            need_promote = node.var
            wire_name = "parselect_promoted_{}".format(
                len(self.promoted_wires))
            promoted_var = vast.Identifier(wire_name)
            node.var = promoted_var
            self.promoted_wires.append((promoted_var, need_promote))