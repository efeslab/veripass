import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getWidth, getConstantWidth
from utils.ValueParsing import verilog_string_to_int


class WidthPass(PassBase):
    """
    Will add a `widthtbl` map in pass_state
    the map is { vast.Node -> int }
    """

    def __init__(self, pass_state):
        # Do not fallback to visit_children
        super().__init__(pass_state, False)
        self.state.widthtbl = {}
        self.widthtbl = self.state.widthtbl
        self.identifierRef = self.state.identifierRef
        self.typeInfo = self.state.typeInfo
        assert((self.identifierRef is not None)
               and (self.typeInfo is not None))

    def visit_ModuleDef(self, node):
        for item in node.items:
            if not isinstance(item, vast.Variable):
                self.visit(item)

    def visit_Always(self, node):
        self.visit(node.statement)

    def visit_Constant(self, node):
        width = getConstantWidth(node)
        if width:
            self.widthtbl[node] = width

    def visit_LConcat(self, node):
        # Do not expect to see this syntax
        assert(0)

    def visit_Concat(self, node):
        self.visit_children(node)
        width = 0
        for c in node.list:
            assert(isinstance(self.widthtbl[c], int))
            width += self.widthtbl[c]
        self.widthtbl[node] = width

    def visit_Cast(self, node):
        self.visit(node.value)
        self.widthtbl[node] = getWidth(node.width)

    def visit_Repeat(self, node):
        self.visit(node.value)
        assert(isinstance(node.times, vast.IntConst))
        times = verilog_string_to_int(node.times.value)
        self.widthtbl[node] = times * self.widthtbl[node.value]

    def visit_Partselect(self, node):
        self.visit(node.var)
        self.widthtbl[node] = getWidth(node)

    def visit_Pointer(self, node):
        assert(isinstance(node.var, vast.Identifier))
        varref = self.identifierRef[node.var.name]
        vartype = self.typeInfo[varref]
        assert((len(vartype.dimensions) == 1)
               and "TODO: Multi-dimension array handler")
        self.widthtbl[node] = vartype.width

    def visit_Lvalue(self, node):
        self.visit(node.var)
        self.widthtbl[node] = self.widthtbl[node.var]

    def visit_Rvalue(self, node):
        self.visit(node.var)
        self.widthtbl[node] = self.widthtbl[node.var]

    def visit_UnaryOperator(self, node):
        self.visit(node.right)
        # the resulting width is the same as the operand's width
        same_width_operators = set([
            vast.Unot,  # bitwise operators
            vast.Uplus, vast.Uminus])
        # the resulting width is one bit
        redunction_operators = set(
            [vast.Ulnot, vast.Uand, vast.Unand, vast.Uor, vast.Unor, vast.Uxor, vast.Uxnor])
        onebit_operators = redunction_operators
        if node.__class__ in same_width_operators:
            self.widthtbl[node] = self.widthtbl[node.right]
        elif node.__class__ in onebit_operators:
            self.widthtbl[node] = 1
        else:
            assert(0 and "Unknown unary operator")
    """
    This should handle all binary operators. But there is no BinaryOperator class in pyverilog.
    To make things worse, UnaryOperator is even a subclass of Operator.
    So be care of this weird inheritance.
    """

    def visit_Operator(self, node):
        self.visit(node.left)
        self.visit(node.right)
        # NOTE: I don't know how to determine the width of vast.Power, vast.Divide, vast.Mod.
        # So they are undefined and asserted.
        # the resulting width is the max of both operands' width
        arithmetic_operators = set([vast.Times, vast.Plus, vast.Minus])
        bitwise_operators = set([vast.And, vast.Xor, vast.Xnor, vast.Or])
        maxwidth_operators = arithmetic_operators | bitwise_operators
        # the resulting width is the same as the left hand side
        lhs_operators = set([vast.Sll, vast.Srl, vast.Sla, vast.Sra])
        # the resulting width is one bit
        onebit_operators = set([
            vast.LessThan, vast.GreaterThan, vast.LessEq, vast.GreaterEq,
            vast.Eq, vast.NotEq, vast.Eql, vast.NotEql,
            vast.Land, vast.Lor])
        if node.__class__ in maxwidth_operators:
            left_width = self.widthtbl[node.left]
            right_width = self.widthtbl[node.right]
            assert(left_width == right_width)
            self.widthtbl[node] = max(left_width, right_width)
        elif node.__class__ in lhs_operators:
            self.widthtbl[node] = self.widthtbl[node.left]
        elif node.__class__ in onebit_operators:
            self.widthtbl[node] = 1
        else:
            assert(0 and "Unknown binary operator")

    def visit_Cond(self, node):
        self.visit_children(node)
        true_width = self.widthtbl[node.true_value]
        false_width = self.widthtbl[node.false_value]
        assert(true_width == false_width)
        self.widthtbl[node] = max(true_width, false_width)

    def visit_Instance(self, node):
        for port in node.portlist:
            self.visit(port)

    def visit_PortArg(self, node):
        self.visit_children(node.argname)

    def visit_Identifier(self, node):
        varref = self.identifierRef[node.name]
        t = self.typeInfo[varref]
        assert(t.dimensions is None)
        self.widthtbl[node] = t.width

    def visit_Node(self, node):
        all_children_nodes = set([
            vast.Assign,
            vast.Substitution, vast.BlockingSubstitution, vast.NonblockingSubstitution,
            vast.IfStatement, vast.Block, vast.Initial
        ])
        skip_nodes = set([
            vast.SingleStatement,
            vast.InstanceList
        ])
        if node.__class__ in all_children_nodes:
            self.visit_children(node)
        elif node.__class__ in skip_nodes:
            return
        else:
            assert(0 and "Unhandled Node")
