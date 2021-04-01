import pyverilog.vparser.ast as vast
from passes.common import PassBase
from passes.common import getDimensions
from utils.ValueParsing import verilog_string_to_int


"""
This pass performs a full split to all eligible arrays.
"""

class FixQuartusBRAMInferPass(PassBase):
    def __init__(self, pass_state):
        super().__init__(pass_state, False)

    def visit_ModuleDef(self, node):
        new_items = []
        for item in node.items:
            if isinstance(item, vast.Logic):
                if item.dimensions != None:
                    dims = getDimensions(item.dimensions)
                    assert(len(dims) == 1)
                    if dims[0] >= 32:
                        item.annotation = "synthesis ramstyle = \"MLAB, no_rw_check\""
                    else:
                        item.annotation = "synthesis ramstyle = \"logic\""

