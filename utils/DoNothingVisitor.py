import pyverilog.vparser.ast as vast
from utils.common import ASTNodeVisitor

"""
A visitor that does nothing on the AST.
"""

class DoNothingVisitor(ASTNodeVisitor):
    def __init__(self, const_tbl=None):
        super().__init__(pass_state, False)

    def visit(self, node):
        return node
