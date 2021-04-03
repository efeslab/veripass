import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getWidth, getDimensions, getConstantWidth


class TypeInfo(object):
    """
    width is int
    dimensions is List of int
    """

    def __init__(self, width, dimensions):
        self.width = width
        self.dimensions = dimensions


class TypeInfoPass(PassBase):
    """
    Will add a `typeInfo` map in pass_state
    the map is { vast.Node -> TypeInfo }
    """

    def __init__(self, pm, pass_state):
        # Do not fallback to visit_children
        super().__init__(pm, pass_state, False)
        self.state.typeInfo = {}
        self.typeInfo = self.state.typeInfo

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
        if node.width:
            self.typeInfo[node] = TypeInfo(getWidth(node.width), None)
        elif isinstance(node.value, vast.Constant):
            self.typeInfo[node] = TypeInfo(getConstantWidth(node.value), None)
        else:
            raise NotImplementedError("Unknown Parameter syntax")

    def visit_Ioport(self, node):
        assert(isinstance(node.first, vast.Variable))
        self.visit_Variable(node.first)

    def visit_Variable(self, node):
        if node.width:
            width = getWidth(node.width)
        else:
            assert(node.value is None)
            width = 1
        if node.dimensions:
            dimensions = getDimensions(node.dimensions)
        else:
            dimensions = None
        self.typeInfo[node] = TypeInfo(width, dimensions)

    def isListening(self):
        return True

    def event_new_Variable(self, node):
        self.visit_Variable(node)