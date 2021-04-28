import pyverilog.vparser.ast as vast
from passes.common import PassBase

class VerilatorReTagPass(PassBase):
    """
    Re-tag some annotations with "verilator tag", if they are expected to be parsed by verilator again and should be preserved.
    Unconditionally re-tag:
    1. syscall annotations
    2. TransRecTarget

    Conditionally re-tag:
    1. "synthesis" metacommand
    """

    """
    Configurations
    """
    # whether to re-tag "synthesis" metacommand
    SYNTHESIS_RETAG = True
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, True)

    @classmethod
    def reTagAnno(cls, node):
        if not node.annotation.startswith("verilator tag"):
            node.annotation = "verilator tag " + node.annotation

    def visit_Variable(self, node):
        if node.annotation:
            if node.annotation.startswith("TransRecTarget"):
                self.reTagAnno(node)
            elif node.annotation.startswith("synthesis") and self.SYNTHESIS_RETAG:
                self.reTagAnno(node)

    def visit_SystemCall(self, node):
        if node.annotation:
            self.reTagAnno(node)