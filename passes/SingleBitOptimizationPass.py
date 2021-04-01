import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getDimensions
from utils.ValueParsing import verilog_string_to_int

import copy

"""
Optimize a list of single bit operations. Used in FlowGuard to save logic.
"""

class SingleBitOptimizationPass(PassBase):
    def __init__(self, pass_state):
        super().__init__(pass_state, False)
        try:
            self.const_tbl = self.state.const_tbl
        except:
            self.const_tbl = None

    def visit_IntConst(self, node):
        if node.value == "1":
            return vast.IntConst("1'b1")
        elif node.value == "0":
            return vast.IntConst("1'b0")
        return node

    def visit_Pointer(self, node):
        return node

    def visit_Identifier(self, node):
        if self.const_tbl != None:
            if node.name in self.const_tbl:
                return self.const_tbl[node.name]
        return node

    def visit_Unot(self, node):
        node.right = self.visit(node.right)
        if isinstance(node.right, vast.Unot):
            return node.right.right
        if isinstance(node.right, vast.IntConst):
            if node.right.value == "1'b1":
                return vast.IntConst("1'b0")
            elif node.right.value == "1'b0":
                return vast.IntConst("1'b1")
        # We give up here
        return node

    def visit_And(self, node):
        node.left = self.visit(node.left)
        node.right = self.visit(node.right)
        if isinstance(node.left, vast.IntConst):
            if node.left.value == "1'b1":
                return node.right
            if node.left.value == "1'b0":
                return vast.IntConst("1'b0")
        if isinstance(node.right, vast.IntConst):
            if node.right.value == "1'b1":
                return node.left
            if node.right.value == "1'b0":
                return vast.IntConst("1'b0")
        if node.left == node.right:
            return node.left
        if isinstance(node.right, vast.And):
            # A & (A & B) --> A & B
            if node.left == node.right.left:
                return node.right
            # A & (B & A) --> B & A
            if node.left == node.right.right:
                return node.right
        if isinstance(node.left, vast.And):
            # (A & B) & A --> A & B
            if node.left.left == node.right:
                return node.left
            # (B & A) & A --> B & A
            if node.left.right == node.right:
                return node.right
        return node

    def visit_Or(self, node):
        node.left = self.visit(node.left)
        node.right = self.visit(node.right)
        if isinstance(node.left, vast.IntConst):
            if node.left.value == "1'b1":
                return vast.IntConst("1'b1")
            if node.left.value == "1'b0":
                return node.right
        if isinstance(node.right, vast.IntConst):
            if node.right.value == "1'b1":
                return vast.IntConst("1'b1")
            if node.right.value == "1'b0":
                return node.left
        if node.left == node.right:
            return node.left
        if isinstance(node.right, vast.Or):
            # A | (A | B)
            if node.left == node.right.left:
                return node.right
            # A | (B | A)
            if node.left == node.right.right:
                return node.right
        if isinstance(node.left, vast.Or):
            # (A | B) | A
            if node.right == node.left.left:
                return node.left
            # (B | A) | B
            if node.right == node.left.right:
                return node.left
        return node

    def visit_Cond(self, node):
        node.cond = self.visit(node.cond)
        node.true_value = self.visit(node.true_value)
        node.false_value = self.visit(node.false_value)
        if isinstance(node.cond, vast.IntConst):
            if node.cond.value == "1'b1":
                return node.true_value
            if node.cond.value == "1'b0":
                return node.false_value
        return node
