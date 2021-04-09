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
    Require the analysis result of "WidthPass"

    Will instrument task-related supporting code:
    1. Add a cycle counter addition always block
    2. Promote the path constraints of display tasks as new wires
    3. Instantiate a SignalTapII IP to trace both path constraints and the args of display tasks
    Will add the following vast node to pass_state:
    1. `cycle_cnt` (vast.Identifier), a cycle counter for $time
    2. `reset` (vast.Identifier), the reset signal
    """

    """
    Configurations:
    1. CYCLE_COUNTER_WIDTH: the width of the cycle counter register
    2. CYCLE_COUNTER_NAME: the name of the cycle counter register
    """
    CYCLE_COUNTER_WIDTH = 64
    CYCLE_COUNTER_NAME = "TASKPASS_cycle_counter"
    INSTRUMENT_SWEEP = False
    INSTRUMENT_SWEEP_CFG_WIDTH = None  # should be int, Up to 2^12, 4096 bits
    INSTRUMENT_SWEEP_CFG_DEPTH = None  # should be int, Up to 2^17, 128K samples

    def __init__(self, pm, pass_state, cycle_cnt_name=CYCLE_COUNTER_NAME,
                 cnt_width=CYCLE_COUNTER_WIDTH):
        # Allow fallback to visit_children
        super().__init__(pm, pass_state, True)
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
        # instrumentation related
        self.cnt = vast.Identifier(cycle_cnt_name)
        self.cnt_name = cycle_cnt_name
        self.cnt_width = cnt_width
        # update pass_state
        self.state.cycle_cnt = self.cnt

    def visit_ModuleDef(self, node):
        # self.inferred_clock contains all sens of all always to which display tasks belong
        # it is a dict {str(identifier name) => int (frequency)}
        self.inferred_clock = {}
        for c in node.items:
            # filter all variable items, since there will be no tasks
            if not isinstance(c, vast.Variable):
                self.visit(c)
        # choose the most frequently used clock signal
        clock_name, freq = max(self.inferred_clock.items(), key=lambda x: x[1])
        clock = vast.Identifier(clock_name)
        new_cnt_def, new_cnt_always = self.create_cycle_counter_statements(
            clock)
        if self.INSTRUMENT_SWEEP:
            cond_wire_defs, stp_instance = self.getFakeSTPInstrumentation(
                clock)
        else:
            cond_wire_defs, stp_instance = self.getSTPInstrumentation(clock)
        node.items.insert(0, new_cnt_def)
        node.items.append(new_cnt_always)
        node.items.extend(cond_wire_defs)
        node.items.append(stp_instance)

    def visit_Always(self, node):
        # self.always is to track the senslist of always to which each display tasks belong
        self.always = node
        self.if_cond_stack = IfConditionStack()
        self.visit_children(node)
        self.always = None

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
        # display could also appear in the initial block, which we will skip
        if self.always and node.syscall == "display" and node.anno and node.anno == "debug_display":
            # track sens list for clock inference
            for sens in self.always.sens_list.list:
                # display are assumed to only be sensitive to simple identifiers
                assert(isinstance(sens.sig, vast.Identifier))
                self.inferred_clock[sens.sig.name] = self.inferred_clock.get(
                    sens.sig.name, 0) + 1
            # track path constraints
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

    def getSTPInstrumentation(self, clk):
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
            "acq_data_in": trace_data,
            "acq_trigger_in": vast.Ulnot(self.state.reset),
            "storage_enable": trace_enable_signal,
            "acq_clk": clk
        }
        stp_config = IntelSignalTapIIConfig(stp_port_config)
        stp_config.param_config["SLD_DATA_BITS"] = total_trace_width
        stpinstance = IntelSignalTapII(stp_config)
        return (cond_wire_defs, stpinstance.getInstance())

    def getFakeSTPInstrumentation(self, clk):
        """
        Instrument STP to understand the resource overhaed over a given sweep of data width and sample depth.
        The instrtumentation will only record garbage data constructed from the cycle counter
        """
        # full cnt data without partselect
        cnt_data = [self.cnt for i in range(
            self.INSTRUMENT_SWEEP_CFG_WIDTH // self.cnt_width)]
        remain_width = self.INSTRUMENT_SWEEP_CFG_WIDTH % self.cnt_width
        if remain_width > 0:
            w = getWidthFromInt(remain_width)
            cnt_data.append(vast.Partselect(self.cnt, w.msb, w.lsb))
        fake_data_in = vast.Concat(cnt_data)
        stp_port_config = {
            "acq_data_in": fake_data_in,
            "acq_trigger_in": vast.Ulnot(self.state.reset),
            "storage_enable": vast.IntConst("1"),
            "acq_clk": clk
        }
        stp_config = IntelSignalTapIIConfig(stp_port_config)
        stp_config.param_config["SLD_DATA_BITS"] = self.INSTRUMENT_SWEEP_CFG_WIDTH
        stp_config.param_config["SLD_SAMPLE_DEPTH"] = self.INSTRUMENT_SWEEP_CFG_DEPTH
        stpinstance = IntelSignalTapII(stp_config)
        return ([], stpinstance.getInstance())

    def create_cycle_counter_statements(self, clk):
        """
        Return: [logic declaration, always_block]
        Which first declare the cycle counter logic, then instrument an always block to reset and increment it.
        """

        new_logic = vast.Logic(self.cnt_name, getWidthFromInt(self.cnt_width))
        self.notify_new_Variable(new_logic)
        sens_list = vast.SensList([vast.Sens(clk)])
        always_statement = vast.Block([
            vast.IfStatement(self.state.reset,
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
        return (new_logic, new_always)
