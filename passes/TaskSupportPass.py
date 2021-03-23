import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getWidthFromInt


class TaskSupportPass(PassBase):
    """
    Will instrument task-related supporting code.
    Including:
    1. cycle counter for $time.
        a. Will add `cycle_cnt` (vast.Identifier) to pass_state
    2. Track $display arguments except for formatting string
        a. Will add `display_args` (set of vast.Node) to pass_state
    """

    """
    Configurations:
    1. CYCLE_COUNTER_WIDTH: the width of the cycle counter register
    2. CYCLE_COUNTER_NAME: the name of the cycle counter register
    """
    CYCLE_COUNTER_WIDTH = 64
    CYCLE_COUNTER_NAME = "TASKPASS_cycle_counter"
    CYCLE_NAME = "pClk"
    RESET_NAME = "pck_cp2af_softReset"

    def __init__(self, pass_state,
                 cycle_name=CYCLE_NAME, reset_name=RESET_NAME,
                 cycle_cnt_name=CYCLE_COUNTER_NAME, cnt_width=CYCLE_COUNTER_WIDTH):
        # Allow fallback to visit_children
        super().__init__(pass_state, True)
        self.clk = vast.Identifier(cycle_name)
        self.reset = vast.Identifier(reset_name)
        self.cnt = vast.Identifier(cycle_cnt_name)
        self.cnt_width = cnt_width
        # update pass_state
        self.state.display_args = set()
        self.display_args = self.state.display_args
        self.state.cycle_cnt = self.cnt

    """
    Return: [logic declaration, always_block]
    Which first declare the cycle counter logic, then instrument an always block to reset and increment it.
    """

    def create_cycle_counter_statements(self):
        new_logic = vast.Logic(self.CYCLE_COUNTER_NAME,
                               getWidthFromInt(self.CYCLE_COUNTER_WIDTH))
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
        for c in node.items:
            # filter all variable items, since there will be no tasks
            if not isinstance(c, vast.Variable):
                self.visit(c)
        node.items = self.create_cycle_counter_statements() + node.items

    def visit_SystemCall(self, node):
        if node.syscall == "display":
            for arg in node.args:
                if isinstance(arg, vast.StringConst):
                    continue
                elif isinstance(arg, vast.SystemCall) and arg.syscall == "time":
                    self.display_args.add(self.cnt)
                else:
                    self.display_args.add(arg)
