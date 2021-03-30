import pyverilog.vparser.ast as vast
from passes.WidthPass import WidthVisitor
from utils.common import ASTNodeVisitor
"""
BitwiseToLogicalVisitor converts bit-wise operators on 1-bit signals to logical operators.
It can only handle boolean expression used in if-statements.
This is useful when doing boolean expression simplification.
This visitor requires the analysis result of WidthPass

.visit(node) returns the converted AST

FIXME: this pass updates the results of "WidthPass". Should be more careful about such multi-writer situation.
"""


class BitwiseToLogicalVisitor(ASTNodeVisitor):
    def __init__(self, pass_state):
        super().__init__(self.visit_generic)
        self.width_visitor = WidthVisitor(pass_state)
        self.widthtbl = self.width_visitor.widthtbl
        # init generic rules
        self.allowed_recursive = set([
            vast.Pointer, vast.Operator, vast.Cond, vast.Concat
        ])
        self.identity_classes = set([
            vast.Identifier,
            vast.Constant
        ])

    # Unot is bit-wise ~
    # Ulnot is logical !

    def visit_Unot(self, node):
        right = self.visit(node.right)
        if self.width_visitor.getWidth(right) == 1:
            newnode = vast.Ulnot(right)
            return newnode
        elif right != node.right:
            return vast.Unot(right)
        else:
            return node

    def visit_And(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        if self.width_visitor.getWidth(left) == 1 and self.width_visitor.getWidth(right) == 1:
            newnode = vast.Land(left, right)
            return newnode
        elif left != node.left or right != node.right:
            return vast.And(left, right)
        else:
            return node

    def visit_Or(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        if self.width_visitor.getWidth(left) == 1 and self.width_visitor.getWidth(right) == 1:
            newnode = vast.Lor(left, right)
            return newnode
        elif left != node.left or right != node.right:
            return vast.Or(left, right)
        else:
            return node

    def visit_Xor(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        if self.width_visitor.getWidth(left) == 1 and self.width_visitor.getWidth(right) == 1:
            # a ^ b == (a && !b) || (!a && b)
            return vast.Lor(
                vast.Land(left, vast.Ulnot(right)),
                vast.Land(vast.Ulnot(left), right))
        elif left != node.left or right != node.right:
            return vast.Xor(left, right)
        else:
            return node

    def visit_Xnor(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        if self.width_visitor.getWidth(left) == 1 and self.width_visitor.getWidth(right) == 1:
            # a ^ b == (a && !b) || (!a && b)
            return vast.Lor(
                vast.Land(left, right),
                vast.Land(vast.Ulnot(left), vast.Ulnot(right)))
        elif left != node.left or right != node.right:
            return vast.Xnor(left, right)
        else:
            return node

    def visit_Partselect(self, node):
        var = self.visit(node.var)
        if var != node.var:
            newnode = vast.Partselect(var, node.msb, node.lsb)
            return newnode
        else:
            return node

    def visit_generic(self, node):
        for cl in node.__class__.mro():
            if cl in self.allowed_recursive:
                oldchildren = node.children()
                newchildren = tuple([self.visit(c) for c in node.children()])
                if oldchildren != newchildren:
                    newnode = node.__class__(*newchildren)
                    return newnode
                else:
                    return node
            elif cl in self.identity_classes:
                return node
        raise NotImplementedError("Unknown node class")
