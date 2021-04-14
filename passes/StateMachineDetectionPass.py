import pyverilog.vparser.ast as vast
from passes.common import PassBase

from pyverilog.dataflow.modulevisitor import ModuleVisitor
from pyverilog.dataflow.signalvisitor import SignalVisitor
from pyverilog.dataflow.bindvisitor import BindVisitor
import pyverilog.dataflow.dataflow as df
import pyverilog.utils.util as util

"""
First, detect candidate FSM variables in the rtl code.
A candidate FSM variable must be referenced in an Eq statement in
the condition of an IfStatement.
"""

class _StateMachineCandidatePass(PassBase):
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, True)
        self.state.fsm_candidate = set()
        self.ifcondcnt = 0

    def visit_IfStatement(self, node):
        self.ifcondcnt += 1
        self.visit(node.cond)
        self.ifcondcnt -= 1
        if node.true_statement != None:
            self.visit(node.true_statement)
        if node.false_statement != None:
            self.visit(node.false_statement)

    def visit_Cond(self, node):
        self.ifcondcnt += 1
        self.visit(node.cond)
        self.ifcondcnt -= 1
        if node.true_value:
            self.visit(node.true_value)
        if node.false_value:
            self.visit(node.false_value)

    def visit_Eq(self, node):
        if self.ifcondcnt > 0:
            if isinstance(node.left, vast.IntConst) and isinstance(node.right, vast.Identifier):
                self.state.fsm_candidate.add(node.right)
            if isinstance(node.left, vast.Identifier) and isinstance(node.right, vast.IntConst):
                self.state.fsm_candidate.add(node.left)

class _StateMachineCandidateFilterPass(PassBase):
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, True)
        assert(hasattr(self.state, "fsm_candidate"))
        self.invalid_fsm_op_stack = []
        self.valid_fsm_ops = {"Eq", "NotEq"}

    def visit_UnaryOperator(self, node):
        self.visit(node.right)

    def visit_Cond(self, node):
        self.visit(node.cond)
        if node.true_value:
            self.visit(node.true_value)
        if node.false_value:
            self.visit(node.false_value)

    def visit_Operator(self, node):
        if node.left in self.state.fsm_candidate:
            if not node.__class__.__name__ in self.valid_fsm_ops:
                self.state.fsm_candidate.remove(node.left)
        if node.right in self.state.fsm_candidate:
            if not node.__class__.__name__ in self.valid_fsm_ops:
                self.state.fsm_candidate.remove(node.right)
        pushed = False
        if not node.__class__.__name__ in self.valid_fsm_ops:
            pushed = True
            self.invalid_fsm_op_stack.append(node.__class__.__name__)
        self.visit(node.left)
        self.visit(node.right)
        if pushed:
            self.invalid_fsm_op_stack.pop()

    def visit_Concat(self, node):
        if len(self.invalid_fsm_op_stack) > 0:
            for n in node.list:
                if n in self.state.fsm_candidate:
                    self.state.fsm_candidate.remove(n)


"""
An FSM variable control-depend on itself.
"""

class DFSelfControlDepVisitor:
    def __init__(self, terms, binddict, target):
        self.terms = terms
        self.binddict = binddict
        self.incondnode = False
        self.target = target
        self.valid_fsm_ops = {"Eq", "NotEq"}

    def is_reg(self, termname):
        if not termname in self.binddict:
            # If termname does not exist in binddict, the variable is never
            # assigned, so we return None here.
            return None
        if self.binddict[termname][0].parameterinfo == "nonblocking":
            return True
        return False

    def visit(self, node):
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        r = visitor(node)
        return r

    def generic_visit(self, node):
        for child in node.children():
            if self.visit(child):
                return True
        return False

    def visit_DFTerminal(self, node):
        termname = node.name
        r = self.is_reg(termname)
        if r == True or self.incondnode:
            return False
        elif r == False:
            for n in self.binddict[termname]:
                if self.visit(n.tree):
                    return True
            return False
        else:
            return False

    def visit_DFOperator(self, node):
        if self.incondnode:
            if node.operator in self.valid_fsm_ops:
                if isinstance(node.nextnodes[0], df.DFIntConst) and isinstance(node.nextnodes[1], df.DFTerminal):
                    if node.nextnodes[1].name == self.target:
                        return True
                if isinstance(node.nextnodes[0], df.DFTerminal) and isinstance(node.nextnodes[1], df.DFIntConst):
                    if node.nextnodes[0].name == self.target:
                        return True
        for n in node.nextnodes:
            if self.visit(n):
                return True
        return False

    def visit_DFBranch(self, node):
        if node.truenode != node.falsenode:
            self.incondnode = True
            if self.visit(node.condnode):
                self.incondnode = False
                return True
            self.incondnode = False
        if node.truenode and self.visit(node.truenode):
            return True
        if node.falsenode and self.visit(node.falsenode):
            return True
        return False


"""
Detect FSM variables in two steps:
1. Detect a bunch of candidates that are referenced in an Eq statement in the
   condition of an IfStatement.
2. If a candidate control-depend on itself, it's considered as an FSM variable.
"""
class StateMachineDetectionPass(PassBase):
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, False)
        self.candidate_pass = _StateMachineCandidatePass(pm, pass_state)
        self.candidate_filter_pass = _StateMachineCandidateFilterPass(pm, pass_state)
        if hasattr(self.state, "terms") and hasattr(self.state, "binddict"):
            pass
        else:
            self.state.terms = None
            self.state.binddict = None

        self.state.fsm = set()

        assert(hasattr(self.state, "top_module"))
        assert(hasattr(self.state, "model_list"))

    def visit(self, node):
        if self.state.terms == None or self.state.binddict == None:
            module_visitor = ModuleVisitor()
            module_visitor.visit(node)
            modulenames = module_visitor.get_modulenames()
            moduleinfotable = module_visitor.get_moduleinfotable()

            signal_visitor = SignalVisitor(moduleinfotable, self.state.top_module)
            for m in self.state.model_list:
                signal_visitor.addBlackboxModule(m[0], m[1])
            signal_visitor.start_visit()
            frametable = signal_visitor.getFrameTable()

            # BindVisitor's reorder is buggy for SSSP, so we turn off reorder here.
            bind_visitor = BindVisitor(moduleinfotable, self.state.top_module, frametable,
                    noreorder=True, ignoreSyscall=True)
            for m in self.state.model_list:
                bind_visitor.addBlackboxModule(m[0], m[1])
            bind_visitor.start_visit()
            dataflow = bind_visitor.getDataflows()

            self.state.terms = dataflow.getTerms()
            self.state.binddict = dataflow.getBinddict()

        terms = self.state.terms
        binddict = self.state.binddict

        self.candidate_pass.visit(node)
        self.candidate_filter_pass.visit(node)
        for cand in self.state.fsm_candidate:
            termname = util.toTermname(self.state.top_module + "." + cand.name)
            v = DFSelfControlDepVisitor(terms, binddict, termname)
            for i in binddict[termname]:
                r = v.visit(i.tree)
                if r:
                    self.state.fsm.add(cand)
                    break


