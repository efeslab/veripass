import sympy.logic.boolalg as boolalg
import pyverilog.vparser.ast as vast
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator

from passes.common import PassBase
from passes.common import getWidthFromInt
from passes.WidthPass import WidthVisitor
from utils.BitwiseToLogicalVisitor import BitwiseToLogicalVisitor
from utils.SymPyUtils import CondASTToSymPyVisitor
from utils.SymPyUtils import CondSymPyToASTVisitor
from utils.IntelSignalTapII import IntelSignalTapIIConfig, IntelSignalTapII

from functools import reduce

"""
Configurations:
1. CYCLE_COUNTER_WIDTH: the width of the cycle counter register
2. CYCLE_COUNTER_NAME: the name of the cycle counter register
"""
CYCLE_COUNTER_WIDTH = 64
CYCLE_COUNTER_NAME = "TASKPASS_cycle_counter"
CYCLE_NAME = "pClk"
RESET_NAME = "pck_cp2af_softReset"


class IfConditionStack(object):
    """
    IfConditionStack manages the path constraint of multiple-level if-statements.
    It maintains a stack-top condition (self.cond_top, a vast.Node) to represent the constraint of current path.
    self.cond_top is an unbalanced, left-hand-side recurrent vast.Land tree:
      e.g. `a && b && c && d` becomes `Land(Land(Land(a,b),c),d)`
    """

    def __init__(self):
        self.stack = []
        self.cond_top = None

    def push(self, cond):
        """
        cond is vast.Node
        """

        self.stack.append(cond)
        if self.cond_top is None:
            self.cond_top = cond
        else:
            self.cond_top = vast.Land(self.cond_top, cond)

    def pop(self):
        """
        Return: vast.Node, the popped-out condition
        """

        cond = self.stack.pop()
        if isinstance(self.cond_top, vast.Land):
            # Non-top-level condition, take the left-hand-side subtree
            self.cond_top = self.cond_top.left
        else:
            # Top-level condition
            self.cond_top = None

    def getCond(self):
        return self.cond_top


class TaskSupportPass(PassBase):
    """
    Will collect task-related info:
    1. Track $display arguments except for formatting string
        TODO: revisit this document
        a. Will add `display_args` (dict of {vast.Node, vast.Node}) to pass_state
            each entry maps a display argument to accumulated conditions.

    Require the analysis result of "WidthPass"
    """

    def __init__(self, pass_state):
        # Allow fallback to visit_children
        super().__init__(pass_state, True)
        self.bitwise2logical = BitwiseToLogicalVisitor(pass_state)
        self.ast2sympy = CondASTToSymPyVisitor()
        self.sympy2ast = CondSymPyToASTVisitor(self.ast2sympy.rsymbolmap)
        # display_arg2cond tracks a list of path constraint for each unique display argument.
        # e.g. if (A) display(x)
        #      if (B) ... else display(x)
        # then there should be x => [A, !B]
        # x is sympy.Symbol and A, B are sympy expressions
        # {sympy.Symbol => [SymPy expressions]}
        self.display_arg2cond = {}
        # display_cond2arg is a dict {sympy expressions => [sympy.Symbol]}
        self.display_cond2arg = {}
        # dict {sympy expressions => vast.Node (display expression)}
        self.display_cond2display = {}
        self.cnt = self.state.cycle_cnt

    def visit_ModuleDef(self, node):
        for c in node.items:
            # filter all variable items, since there will be no tasks
            if not isinstance(c, vast.Variable):
                self.visit(c)
        cond_wire_defs, stp_instance = self.getSTPInstrumentation()
        node.items.extend(cond_wire_defs)
        node.items.append(stp_instance)

    def visit_Always(self, node):
        self.if_cond_stack = IfConditionStack()
        self.visit_children(node)

    def visit_IfStatement(self, node):
        if node.true_statement:
            # visit true branch
            self.if_cond_stack.push(node.cond)
            self.visit(node.true_statement)
            self.if_cond_stack.pop()
        if node.false_statement:
            # visit false branch
            self.if_cond_stack.push(vast.Ulnot(node.cond))
            self.visit(node.false_statement)
            self.if_cond_stack.pop()

    def visit_SystemCall(self, node):
        if node.syscall == "display":
            cond = self.if_cond_stack.getCond()
            cond_converted = self.bitwise2logical.visit(cond)
            # this simplify convert conditions to CNF
            sympy_cond = boolalg.simplify_logic(
                self.ast2sympy.visit(cond_converted))
            cond2arg = self.display_cond2arg.setdefault(sympy_cond, [])
            self.display_cond2display[sympy_cond] = node
            for arg in node.args:
                if isinstance(arg, vast.StringConst):
                    continue
                elif isinstance(arg, vast.SystemCall) and arg.syscall == "time":
                    sympy_arg = self.ast2sympy.visit(self.cnt)
                else:
                    sympy_arg = self.ast2sympy.visit(arg)
                cond2arg.append(sympy_arg)
                self.display_arg2cond.setdefault(
                    sympy_arg, []).append(sympy_cond)

    def get_cond_wires(self, all_conds):
        """
        all_conds are list of vast.Node. Each element represents a path constraints of a display task
        Return: ([new Wire declarateion and Assign statements], [vast.Identifier of all condition wires])
        """

        new_module_items = []
        all_cond_wire_identifiers = []
        for cid, cond in enumerate(all_conds):
            wire_name = "display_cond_{}".format(cid)
            new_wire = vast.Wire(wire_name)
            identifier = vast.Identifier(wire_name)
            new_assign = vast.Assign(identifier, cond)
            new_module_items.append(new_wire)
            new_module_items.append(new_assign)
            all_cond_wire_identifiers.append(identifier)
        return (new_module_items, all_cond_wire_identifiers)

    def getSTPInstrumentation(self):
        # encode display path constriants/conditions
        cond2id = {}
        all_conds = []
        for cid, cond in enumerate(self.display_cond2arg.keys()):
            all_conds.append(self.sympy2ast.visit(cond))
            cond2id[cond] = cid
        # encode display args
        # arg2range is {sympy.Symbol => (start_index, end_index)}
        arg2range = {}
        all_args = []
        args_width_accu = 0
        width_visitor = WidthVisitor(self.state)
        for arg in self.display_arg2cond.keys():
            ast_arg = self.sympy2ast.visit(arg)
            all_args.append(ast_arg)
            arg_width = width_visitor.getWidth(ast_arg)
            arg2range[arg] = (args_width_accu, args_width_accu + arg_width - 1)
            args_width_accu += arg_width
        total_trace_width = len(all_conds) + args_width_accu
        # cond_wire_identifiers has new defined wires, thus WidthVisitor cannot operate on them.
        cond_wire_defs, cond_wire_identifiers = self.get_cond_wires(all_conds)
        trace_enable_signal = reduce(vast.Lor, cond_wire_identifiers)
        trace_data = vast.Concat(cond_wire_identifiers + all_args)
        stp_port_config = {
            "acq_data_in" : trace_data,
            "acq_trigger_in" : vast.Ulnot(self.state.reset),
            "storage_enable" : trace_enable_signal,
            "acq_clk" : self.state.clk
        }
        stp_config = IntelSignalTapIIConfig(stp_port_config)
        stp_config.param_config["SLD_DATA_BITS"] = total_trace_width
        stpinstance = IntelSignalTapII(stp_config)
        return (cond_wire_defs, stpinstance.getInstance())


class TaskSupportInstrumentationPass(PassBase):
    """
    Will instrument task-related supporting code:
    1. A cycle counter addition always block
    Will add the following vast node to pass_state:
    1. `cycle_cnt` (vast.Identifier), a cycle counter for $time
    2. `clk` (vast.Identifier), the input clock signal
    3. `reset` (vast.Identifier), the reset signal
    """

    def __init__(self, pass_state,
                 cycle_name=CYCLE_NAME, reset_name=RESET_NAME,
                 cycle_cnt_name=CYCLE_COUNTER_NAME, cnt_width=CYCLE_COUNTER_WIDTH):
        super().__init__(pass_state, False)
        # define shared Identifiers
        self.clk = vast.Identifier(cycle_name)
        self.reset = vast.Identifier(reset_name)
        self.cnt = vast.Identifier(cycle_cnt_name)
        # save cycle counter settings
        self.cycle_cnt_name = cycle_cnt_name
        self.cnt_width = cnt_width
        # update pass_state
        self.state.cycle_cnt = self.cnt
        self.state.reset = self.reset
        self.state.clk = self.clk

    """
    Return: [logic declaration, always_block]
    Which first declare the cycle counter logic, then instrument an always block to reset and increment it.
    """

    def create_cycle_counter_statements(self):
        new_logic = vast.Logic(self.cycle_cnt_name,
                               getWidthFromInt(self.cnt_width))
        sens_list = vast.SensList([vast.Sens(self.clk)])
        always_statement = vast.Block([
            vast.IfStatement(self.reset,
                             # cnt <= 64'h0
                             vast.NonblockingSubstitution(
                                 self.cnt, vast.IntConst("{}'h0".format(self.cnt_width))),
                             # cnt <= cnt + 64'h1
                             vast.NonblockingSubstitution(self.cnt,
                                                          vast.Plus(self.cnt,
                                                                    vast.IntConst(
                                                                        "{}'h1".format(self.cnt_width))
                                                                    )
                                                          )
                             )
        ])
        new_always = vast.Always(sens_list, always_statement)
        return [new_logic, new_always]

    def visit_ModuleDef(self, node):
        node.items = self.create_cycle_counter_statements() + node.items
