import pyverilog.vparser.ast as vast
from utils.ValueParsing import verilog_string_to_int


class PassState(object):
    pass

# This comes from pyverilog.dataflow.visit.NodeVisitor


class PassBase(object):
    def __init__(self, pass_state, allowFallback=False):
        # for debugging purpose
        self.stack = []
        self.allowFallback = allowFallback
        self.state = pass_state

    def visit(self, node):
        self.stack.append((node.__class__, node))
        visitor = None
        #　search through the inheritance chain for an existing visit_XXX function
        for cl in node.__class__.mro():
            method = 'visit_' + cl.__name__
            visitor = getattr(self, method, None)
            if visitor is not None:
                break
        ret = None
        if visitor is not None:
            ret = visitor(node)
        elif self.allowFallback:
            self.visit_children(node)
        else:
            raise NotImplementedError("Cannot find a call back")
        self.stack.pop()
        return ret

    def visit_children(self, node):
        for c in node.children():
            self.visit(c)


class PassManager(object):
    def __init__(self):
        self.state = PassState()
        self.registred_pass = set()
        # The order matters. Currently, pass dependencies are maintained manually
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
