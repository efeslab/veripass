import pyverilog.vparser.ast as vast
from passes.common import PassBase

"""
TODO:
1. support variables defined in different scopes, e.g. module, always, block, etc.
    This pass currently maintains a global name->vast.Node mapping
"""


class IdentifierRefPass(PassBase):
    """
    Will add an `identifierRef` map in pass_state
    The map is {str -> vast.Node}
    """

    def __init__(self, pm, pass_state):
        # Do not fallback to visit_children
        super().__init__(pm, pass_state, False)
        self.state.identifierRef = {}
        self.identifierRef = self.state.identifierRef

    def visit_ModuleDef(self, node):
        for param in node.paramlist.params:
            self.visit(param)
        for port in node.portlist.ports:
            # this is vast.Ioport
            self.visit(port)
        for item in node.items:
            if isinstance(item, vast.Variable):
                self.visit(item)

    def visit_Parameter(self, node):
        self.identifierRef[node.name] = node

    def visit_Ioport(self, node):
        assert(isinstance(node.first, vast.Variable))
        self.visit_Variable(node.first)

    def visit_Variable(self, node):
        self.identifierRef[node.name] = node

    def isListening(self):
        return True

    def event_new_Variable(self, node):
        self.visit_Variable(node)
