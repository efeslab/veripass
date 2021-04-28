import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getDimensions
from passes.WidthPass import WidthPass, WidthVisitor
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator
from utils.ValueParsing import verilog_string_to_int

"""
A pass that checks the boundary of array access.
Currently only support sequential logic.
"""

class ArrayBoundaryCheckPass(PassBase):
    """
    Assume the result from TypeInfoPass, and IdentifierRefPass..
    """
    DISPLAY_TAG = "debug_display_boundary_check"
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, True)
        self.typeInfo = self.state.typeInfo
        self.identifierRef = self.state.identifierRef
        self.instrument = []
        self.assign_instrument = []
        # instrumented_pair is a set of (Pointer.var.name, codegen(Pointer.ptr)), i.e. a set of tuples of strings
        self.instrumented_pair = set() # should be cleared together with self.instrument
        self.assign_instrumented_pair = set() # no need to clear
        self.temp_wire_id = 0
        self.in_assign = False
        self.widthVisitor = WidthVisitor(pass_state)
        # codegen, used to generate the string representation of ptr expressions
        self.codegen = ASTCodeGenerator()

    def get_temp_wire_name(self):
        self.temp_wire_id += 1
        return "array_boundary_violated_{}".format(self.temp_wire_id)

    def visit_Pointer(self, node):
        if isinstance(node.ptr, vast.IntConst):
            return node
        varref = self.identifierRef[node.var.name]
        vartype = self.typeInfo[varref]
        assert(len(vartype.dimensions) == 1)
        dims = vartype.dimensions
        assert(len(dims) == 1)
        assert(dims[0] >= 0)
        if dims[0] == 0:
            return node
        ptrWidth = self.widthVisitor.getWidth(node.ptr)
        assert(isinstance(node.var, vast.Identifier))
        var_ptr_pair = (node.var.name, self.codegen.visit(node.ptr))
        if dims[0] < (1 << ptrWidth):
            if not self.in_assign and \
                    var_ptr_pair not in self.instrumented_pair and \
                    var_ptr_pair not in self.assign_instrumented_pair:
                # if pointer access it not in assign, the check should performed at the same condition as the pointer access
                # Because the pointer access may not always be valid.
                # If we already checked the same pointer acesss (determined by (node.var.name, codegen(node.ptr))),
                #   no matter in the same block of statements or globally in assign statements, we will skip this check.
                self.instrumented_pair.add(var_ptr_pair)
                self.instrument.append(vast.IfStatement(
                        vast.GreaterEq(node.ptr, vast.IntConst(str(ptrWidth)+"'h"+hex(dims[0])[2:])),
                        vast.SingleStatement(
                            vast.SystemCall("display", [
                                vast.StringConst(str(node.var) + " overflow")
                            ], anno=self.DISPLAY_TAG)),
                        None))
            elif var_ptr_pair not in self.assign_instrumented_pair:
                # For pointer access in assign statements, the check should always performed. But note that when recording, the check is still performed at clock edges.
                # We only skip this type of checks when it has been checked globally (due to other assign statements).c
                self.assign_instrumented_pair.add(var_ptr_pair)
                self.assign_instrument.append(vast.IfStatement(
                        vast.GreaterEq(node.ptr, vast.IntConst(str(ptrWidth)+"'h"+hex(dims[0])[2:])),
                        vast.SingleStatement(
                            vast.SystemCall("display", [
                                vast.StringConst(str(node.var) + " overflow")
                            ], anno=self.DISPLAY_TAG)),
                        None))
        return node

    def visit_IfStatement(self, node):
        node.cond = self.visit(node.cond)
        if node.true_statement != None:
            node.true_statement = self.visit(node.true_statement)
        if node.false_statement != None:
            node.false_statement = self.visit(node.false_statement)
        return node

    def visit_Block(self, node):
        new_statements = []
        for s in node.statements:
            new_statements.append(self.visit(s))
            for i in self.instrument:
                new_statements.append(i)
            self.instrument = []
        node.statements = new_statements
        return node

    def visit_SingleStatement(self, node):
        node.statement = self.visit(node.statement)
        if len(self.instrument) == 0:
            return node
        else:
            instrument = self.instrument
            self.instrument = []
            return vast.Block([node.statement] + instrument)

    def visit_ModuleDef(self, node):
        for item in node.items:
            if isinstance(item, vast.Variable):
                continue
            self.visit(item)
        if len(self.assign_instrument) != 0:
            node.items.append(vast.Always(
                vast.SensList([vast.Sens(vast.Identifier(""), type="all")]),
                vast.Block(self.assign_instrument)))
        return node

    def visit_Always(self, node):
        node.statement = self.visit(node.statement)
        return node

    def visit_Assign(self, node):
        self.in_assign = True
        self.visit(node.left)
        self.visit(node.right)
        self.in_assign = False
        return node

    def visit_Node(self, node):
        self.visit_children(node)
        return node

