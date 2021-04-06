import pyverilog.vparser.ast as vast
from passes.common import PassBase


class Logic2RegPass(PassBase):
    """
    Unconditionally convert logic declaration:
        (1) If in input/output ports, change to wire.
        (2) If inside module, change to reg.
    This is to remove all logic type, which is not supported by verilog.
    Note that the type "reg" has nothing to do with register allocation.
    So in systemverilog, reg is not very different from wire, which is a weird syntax.
    """

    def __init__(self, pm, pass_state):
        # does not fallback to any visitor
        super().__init__(pm, pass_state, False)

    def visit_ModuleDef(self, node):
        new_items = [
            vast.Reg(c.name, c.width, c.signed, c.dimensions,
                     c.value, c.lineno, c.annotation)
            if isinstance(c, vast.Logic) else c
            for c in node.items
        ]
        for port in node.portlist.ports:
            if isinstance(port.second, vast.Logic):
                l = port.second
                port.second = vast.Wire(
                    l.name, l.width, l.signed, l.dimensions, l.value, l.lineno, l.annotation)
        node.items = new_items
