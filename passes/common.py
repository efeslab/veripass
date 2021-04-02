import pyverilog.vparser.ast as vast
from utils.common import ASTNodeVisitor
from utils.ValueParsing import verilog_string_to_int


class PassState(object):
    pass


class PassBase(ASTNodeVisitor):
    def __init__(self, pass_state, allowFallback=False):
        fallback = self.visit_children if allowFallback else None
        super().__init__(fallback)
        self.state = pass_state
        # for debugging purpose
        self.stack = []


"""
PassManager controls the execution of registerred passes.
All pass should have the constructor __init__(pass_state)
"""


class PassManager(object):
    def __init__(self):
        self.state = PassState()
        self.registred_pass = set()
        # The order matters. Currently, pass dependencies are maintained manually
        # TODO: add automatic pass schdeuling with dependency in mind
        self.pass_to_run = []
        self.pass_completed = set()

    def register(self, passClass):
        assert(issubclass(passClass, PassBase))
        self.pass_to_run.append(passClass)
        self.registred_pass.add(passClass)
        self.pass_ret = {}

    def runAll(self, node):
        for p in self.pass_to_run:
            if p in self.pass_completed:
                continue
            else:
                instance = p(self.state)
                self.pass_ret[p] = instance.visit(node)
                self.pass_completed.add(p)
        self.pass_to_run = []


"""
Get a python integer representation of a pyverilog Width (vast.Node)
"""


def getWidth(width):
    if (isinstance(width.msb, vast.IntConst) and isinstance(width.lsb, vast.IntConst)):
        return verilog_string_to_int(width.msb.value) - verilog_string_to_int(width.lsb.value) + 1
    elif width.msb is width.lsb:  # like wire_a[b:b]
        return 1
    elif isinstance(width.msb, vast.Plus) and \
        width.msb.left is width.lsb and isinstance(width.msb.right, vast.IntConst):
        return int(width.msb.right.value) + 1
    else:
        raise NotImplementedError("Cannot parse this width information")


"""
Get a python list of integer representation of a pyverilog Dimensions (the `dimensions` field)
"""


def getDimensions(dimensions):
    return list([getWidth(w) for w in dimensions.lengths])


"""
Get a python integer representation of the width of a vast.Constant
"""


def getConstantWidth(constant):
    if '\'' in constant.value:
        return int(constant.value.split('\'')[0])
    else:
        return None


"""
width is int
Return: vast.Width(width-1, 0)
"""
_IntConst_Zero = vast.IntConst(str(0))


def getWidthFromInt(width):
    return vast.Width(vast.IntConst(str(width-1)), _IntConst_Zero)
