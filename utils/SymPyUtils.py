from sympy import Symbol
import sympy.logic.boolalg as boolalg

from pyverilog.ast_code_generator.codegen import ASTCodeGenerator
import pyverilog.vparser.ast as vast

from utils.common import ASTNodeVisitor
from functools import reduce


class CondASTToSymPyVisitor(ASTNodeVisitor):
    """
    CondASTToSymPyVisitor will convert a pyverilog boolean condition (in if-statements) to a SymPy boolean expression
    Pyverilog identifiers and non-boolean expressions will be mapped to unique SymPy symbols.
    The symbol mapping (vast=>sympy) is cached so you can apply the same CondASTToSymPyVisitor to multiple ASTs and reuse existing sympy symbols.
    The reverse symbol mapping (sympy=>vast) is available as "self.rsymbolmap", which is required to convery sympy expressions back to pyverilog AST.
    .visit(node) returns the converted SymPy boolean expression
    """

    def __init__(self):
        super().__init__(self.visit_generic)
        # str => sympy.Symbol for vast.Identifier and non-boolean expressions (using codegen for expression equalitiy)
        self.symbolmap = {}
        # sympy.Symbol => vast.Node (including both identifiers and non-boolean expressions)
        self.rsymbolmap = {}
        # init generic rules
        self.allowed_nonboolean = set([
            vast.Pointer, vast.Cond, vast.Operator, vast.Partselect
        ])
        self.codegen = ASTCodeGenerator()
        self.nonboolean_cnt = 0

    def visit_Land(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        return boolalg.And(left, right)

    def visit_Lor(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        return boolalg.Or(left, right)

    def visit_Ulnot(self, node):
        expr = self.visit(node.right)
        return boolalg.Not(expr)

    def visit_Identifier(self, node):
        symbol = self.symbolmap.setdefault(node.name, Symbol(node.name))
        self.rsymbolmap.setdefault(symbol, node)
        return symbol

    def get_nonboolean_symbolname(self):
        self.nonboolean_cnt += 1
        return "nonboolean_{}".format(self.nonboolean_cnt)

    def visit_generic(self, node):
        for cl in node.__class__.mro():
            if cl in self.allowed_nonboolean:
                code = self.codegen.visit(node)
                if code in self.symbolmap:
                    symbol = self.symbolmap[code]
                else:
                    symbol = Symbol(self.get_nonboolean_symbolname())
                    self.symbolmap[code] = symbol
                self.rsymbolmap.setdefault(symbol, node)
                return symbol
        raise NotImplementedError("Cannot find a fallback function")


class CondSymPyToASTVisitor(object):
    """
    CondSymPyToASTVisitor will convert a SymPy boolean expression backto pyverilog AST.
    It requires the reverse symbol map generated by CondASTToSymPyVisitor.
    """

    def __init__(self, rsymbolmap):
        self.rsymbolmap = rsymbolmap
        # for debugging purpose
        self.stack = []

    def visit(self, node):
        self.stack.append((node.func, node))
        visitor = None
        method = 'visit_' + node.func.__name__
        visitor = getattr(self, method)
        ret = visitor(node)
        return ret

    def visit_And(self, node):
        children = [self.visit(c) for c in node.args]
        return reduce(vast.Land, children)

    def visit_Or(self, node):
        children = [self.visit(c) for c in node.args]
        return reduce(vast.Lor, children)

    def visit_Not(self, node):
        e = node.args[0]
        return vast.Ulnot(self.visit(e))

    def visit_Symbol(self, node):
        return self.rsymbolmap[node]