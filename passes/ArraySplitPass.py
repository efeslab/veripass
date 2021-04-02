import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getDimensions
from utils.ValueParsing import verilog_string_to_int

import copy

"""
A full split (i.e. splitting an array to N independent variables) can be
performed to an array that is only accessed with a constant index. We need
to determine whether the array is eligible before doing the accutal split.
"""

class _ArrayPointerInfoPass(PassBase):
    """
    Will store the table of array's access info in pass_state

    pass_state.array_access_info[array_name] == {True|False}
    True means the array is eligible to a full split
    """

    def __init__(self, pass_state):
        super().__init__(pass_state, True)
        self.state.array_access_info = {}

    def visit_Pointer(self, node):
        if not node.var.name in self.state.array_access_info:
            self.state.array_access_info[node.var.name] = True
        if not isinstance(node.ptr, vast.IntConst):
            self.state.array_access_info[node.var.name] = False


"""
This pass performs a full split to all eligible arrays.
"""

class _ArrayFullSplitPass(PassBase):
    def __init__(self, pass_state):
        super().__init__(pass_state, False)
        self.array_access_info = self.state.array_access_info

    def visit_ModuleDef(self, node):
        new_items = []
        for item in node.items:
            if isinstance(item, vast.Variable):
                if item.name in self.array_access_info:
                    assert(item.dimensions != None)
                    # access info is True, meaning it can be fully split
                    if self.array_access_info[item.name]:
                        new_name_tmpl = item.name + "__028" + "{}" + "__029"
                        dims = getDimensions(item.dimensions)
                        # Verilator shouldn't generate nested dimensions
                        assert(len(dims) == 1)
                        for i in range(0, dims[0]):
                            new_item = copy.deepcopy(item)
                            new_item.dimensions = None
                            new_item.name = new_name_tmpl.format(i)
                            new_items.append(new_item)
                    else:
                        new_items.append(item)
                else:
                    new_items.append(item)
            else:
                new_items.append(self.visit(item))
        node.items = new_items
        return node

    def visit_Always(self, node):
        node.statement = self.visit(node.statement)
        return node

    def visit_Constant(self, node):
        return node

    def visit_LConcat(self, node):
        # Do not expect to see this syntax
        assert(0 and "LConcat not implemented")

    def visit_Concat(self, node):
        new_list = []
        for l in node.list:
            new_list.append(self.visit(l))
        node.list = new_list
        return node

    def visit_Cast(self, node):
        node.value = self.visit(node.value)
        return node

    def visit_Repeat(self, node):
        node.value = self.visit(node.value)
        return node

    def visit_Partselect(self, node):
        node.var = self.visit(node.var)
        return node

    def visit_Pointer(self, node):
        assert(isinstance(node.var, vast.Identifier))
        assert(node.var.name in self.array_access_info)
        # access info is True, meaning it can be fully split
        if self.array_access_info[node.var.name]:
            assert(isinstance(node.ptr, vast.IntConst))
            new_name_tmpl = node.var.name + "__028" + "{}" + "__029"
            idx = verilog_string_to_int(node.ptr.value)
            new_name = new_name_tmpl.format(idx)
            return vast.Identifier(new_name)
        else:
            return node

    def visit_Lvalue(self, node):
        node.var = self.visit(node.var)
        return node

    def visit_Rvalue(self, node):
        node.var = self.visit(node.var)
        return node

    def visit_UnaryOperator(self, node):
        node.right = self.visit(node.right)
        return node

    def visit_Operator(self, node):
        node.left = self.visit(node.left)
        node.right = self.visit(node.right)
        return node

    def visit_Cond(self, node):
        node.cond = self.visit(node.cond)
        node.true_value = self.visit(node.true_value)
        node.false_value = self.visit(node.false_value)
        return node

    def visit_InstanceList(self, node):
        new_instances = []
        for i in node.instances:
            new_instances.append(self.visit(i))
        node.instances = new_instances
        return node

    def visit_Instance(self, node):
        new_portlist = []
        for p in node.portlist:
            new_portlist.append(self.visit(p))
        node.portlist = new_portlist
        return node

    def visit_PortArg(self, node):
        node.argname = self.visit(node.argname)
        return node

    def visit_Identifier(self, node):
        return node

    def visit_Block(self, node):
        assert(node.statements != None)
        new_statements = []
        for s in node.statements:
            new_statements.append(self.visit(s))
        node.statements = new_statements
        return node

    def visit_Assign(self, node):
        node.left = self.visit(node.left)
        node.right = self.visit(node.right)
        return node

    def visit_Initial(self, node):
        node.statement = self.visit(node.statement)
        return node

    def visit_IfStatement(self, node):
        node.cond = self.visit(node.cond)
        if node.true_statement != None:
            node.true_statement = self.visit(node.true_statement)
        if node.false_statement != None:
            node.false_statement = self.visit(node.false_statement)
        return node
    
    def visit_Substitution(self, node):
        node.left = self.visit(node.left)
        node.right = self.visit(node.right)
        return node

    def visit_SingleStatement(self, node):
        node.statement = self.visit(node.statement)
        return node

    def visit_SystemCall(self, node):
        return node

    def visit_CommentStmt(self, node):
        return node


"""
The interface which calls the info pass and the full split pass.
"""

class ArraySplitPass(PassBase):
    def __init__(self, pass_state):
        super().__init__(pass_state, False)
        self.infopass = _ArrayPointerInfoPass(self.state)
        self.fullsplitpass = _ArrayFullSplitPass(self.state)

    def visit(self, node):
        self.infopass.visit(node)
        self.fullsplitpass.visit(node)

