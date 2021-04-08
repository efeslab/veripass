import pyverilog.vparser.ast as vast
from passes.common import PassBase


"""
Remove the "$stop" systemcall by changing it to a display.
"""

class RemoveStopPass(PassBase):
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, True)

    def visit_SystemCall(self, node):
        if node.syscall == "stop":
            node.syscall = "display"
            node.args = [vast.StringConst("$stop attamped! ignore...")]
