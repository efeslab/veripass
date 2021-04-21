import pyverilog.vparser.ast as vast
from passes.common import PassBase

from pyverilog.dataflow.modulevisitor import ModuleVisitor
from pyverilog.dataflow.signalvisitor import SignalVisitor
from pyverilog.dataflow.bindvisitor import BindVisitor
import pyverilog.dataflow.dataflow as df
import pyverilog.utils.util as util

from passes.PrintTransitionPass import TransRecTarget, target_merge
from passes.FlowGuardInstrumentationPass import DFDataWidthVisitor
from passes.FlowGuardInstrumentationPass import DFBuildAstVisitor

class DataDepEntry:
    def __init__(self, DFTerm, msb=None, lsb=None):
        self.DFTerm = DFTerm
        self.msb = msb
        self.lsb = lsb
        if self.msb:
            assert(self.lsb != None)

    def getName(self):
        if isinstance(self.DFTerm, df.DFPointer):
            return str(self.DFTerm.var.name.scopechain[1])
        elif isinstance(self.DFTerm, df.DFTerminal):
            return str(self.DFTerm.name.scopechain[1])
        else:
            raise NotImplementedError("Invalid DFTerm")
    def getStr(self):
        s = self.getName()
        if self.msb != None:
            s += ("[" + str(self.msb) + ":" + str(self.lsb) + "]")
        return s

    def getTransRecTarget(self):
        if isinstance(self.DFTerm, df.DFPointer):
            ptr = self.DFTerm.ptr
        else:
            ptr = None
        t = TransRecTarget(self.getName(), ptr,
                self.msb, self.lsb)
        return t

"""
Get the control and data dependencies of a given variable.
"""

class DFDependencyVisitor:
    def __init__(self, terms, binddict):
        self.terms = terms
        self.binddict = binddict
        self.control_deps = []
        self.data_deps = []
        self.in_control = False
        self.build_ast_visitor = DFBuildAstVisitor(self.terms, self.binddict)
        self.terminal_stack = []

    def visit(self, node, msb, lsb):
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method)
        visitor(node, msb, lsb)

    def terminal_in_stack(self, termname, msb, lsb):
        for tn, m, l in self.terminal_stack:
            if tn != termname:
                continue
            if m >= msb and l <= lsb:
                return True
        return False

    def visit_DFTerminal(self, node, msb, lsb):
        termname = node.name
        assert(len(termname.scopechain) == 2)

        if self.terminal_in_stack(termname, msb, lsb):
            return

        self.terminal_stack.append((termname, msb, lsb))

        termmeta = self.terms[termname]
        if 'Rename' in termmeta.termtype:
            binds = self.binddict[termname]
            assert(len(binds) == 1)
            bd = binds[0]
            assert(bd.lsb == None and bd.msb == None and bd.ptr == None)
            self.visit(bd.tree, msb, lsb)
            self.terminal_stack.pop()
            return

        if termname in self.binddict:
            changed = False
            for bd in self.binddict[termname]:
                if bd.parameterinfo == "nonblocking":
                    continue
                if bd.lsb == None and bd.msb == None:
                    self.visit(bd.tree, msb, lsb)
                else:
                    bd_msb = bd.msb.eval()
                    bd_lsb = bd.lsb.eval()

                    if bd_msb < lsb or bd_lsb > msb:
                        continue

                    do_lsb = lsb - bd_lsb
                    do_msb = msb - bd_lsb
                    if do_lsb < 0:
                        do_lsb = 0
                    if do_msb > bd_msb - bd_lsb:
                        do_msb = bd_msb - bd_lsb

                    self.visit(bd.tree, do_msb, do_lsb)

                if bd.ptr != None and not isinstance(bd.ptr, df.DFIntConst) and not isinstance(bd.ptr, df.DFEvalValue):
                    old_in_control = self.in_control
                    self.in_control = True
                    wv = DFDataWidthVisitor(self.terms, self.binddict)
                    width = wv.visit(bd.ptr)
                    self.visit(bd.ptr, width-1, 0)
                    self.in_control = old_in_control

                changed = True

            if changed:
                self.terminal_stack.pop()
                return

        if self.in_control:
            self.control_deps.append(DataDepEntry(node, msb, lsb))
        else:
            self.data_deps.append(DataDepEntry(node, msb, lsb))

        self.terminal_stack.pop()

    def visit_DFPointer(self, node, msb, lsb):
        assert(isinstance(node.var, df.DFTerminal))
        if isinstance(node.ptr, df.DFEvalValue) or isinstance(node.ptr, df.DFIntConst):
            pass
        else:
            old_in_control = self.in_control
            self.in_control = True
            wv = DFDataWidthVisitor(self.terms, self.binddict)
            width = wv.visit(node.ptr)
            self.visit(node.ptr, width-1, 0)
            self.in_control = old_in_control

        if self.in_control:
            self.control_deps.append(DataDepEntry(node, msb, lsb))
        else:
            self.data_deps.append(DataDepEntry(node, msb, lsb))

    def visit_DFPartselect(self, node, msb, lsb):
        target_width = msb - lsb + 1
        ps_msb = node.msb.eval()
        ps_lsb = node.lsb.eval()
        ps_width = ps_msb - ps_lsb + 1
        assert(target_width <= ps_width)

        new_lsb = ps_lsb + lsb
        new_msb = ps_lsb + msb
        self.visit(node.var, new_msb, new_lsb)

    def visit_DFBranch(self, node, msb, lsb):
        old_in_control = self.in_control
        self.in_control = True
        wv = DFDataWidthVisitor(self.terms, self.binddict)
        width = wv.visit(node.condnode)
        self.visit(node.condnode, width-1, 0)
        self.in_control = old_in_control

        if node.truenode:
            self.visit(node.truenode, msb, lsb)
        if node.falsenode:
            self.visit(node.falsenode, msb, lsb)

    def visit_DFConcat(self, node, msb, lsb):
        current_lsb = 0
        interested_msb = msb
        interested_lsb = lsb

        for item in reversed(node.nextnodes):
            wv = DFDataWidthVisitor(self.terms, self.binddict)
            width = wv.visit(item)
            assert(width >= 1)
            current_msb = current_lsb + width - 1

            if current_msb < interested_lsb:
                continue
            if current_lsb > interested_msb:
                continue

            do_lsb = interested_lsb - current_lsb
            do_msb = interested_msb - current_lsb
            if do_lsb < 0:
                do_lsb = 0
            if do_msb >= width:
                do_msb = width - 1

            self.visit(item, do_msb, do_lsb)

    def visit_DFOperator(self, node, msb, lsb):
        # Always count all operators
        for n in node.nextnodes:
            wv = DFDataWidthVisitor(self.terms, self.binddict)
            width = wv.visit(n)
            assert(width >= 1)
            self.visit(n, width-1, 0)

    def visit_DFIntConst(self, node, msb, lsb):
        return

    def visit_DFEvalValue(self, node, msb, lsb):
        return


class SignalDependencyPass(PassBase):
    def __init__(self, pm, pass_state):
        super().__init__(pm, pass_state, False)
        if hasattr(self.state, "terms") and hasattr(self.state, "binddict"):
            pass
        else:
            self.state.terms = None
            self.state.binddict = None

        assert(hasattr(self.state, "top_module"))
        assert(hasattr(self.state, "model_list"))
        assert(hasattr(self.state, "targets"))

        self.state.control_deps = []
        self.state.data_deps = []

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

        control_deps = []
        data_deps = []

        for target in self.state.targets:
            assert(isinstance(target, TransRecTarget)) 
            termname = util.toTermname(self.state.top_module+"."+target.name)
            for bd in binddict.get(termname, []):
                dv = DFDependencyVisitor(terms, binddict)
                if bd.msb == None:
                    wv = DFDataWidthVisitor(terms, binddict)
                    width = wv.visit(bd.tree)
                    dv.visit(bd.tree, target.msb, target.lsb)
                elif bd.msb != None:
                    msb = bd.msb.eval()
                    lsb = bd.lsb.eval()

                    if lsb > target.msb:
                        continue
                    if msb < target.lsb:
                        continue

                    do_msb = target.msb - lsb
                    do_lsb = target.lsb - lsb
                    if do_msb >= msb - lsb:
                        do_msb = msb - lsb
                    if do_lsb < 0:
                        do_lsb = 0

                    dv.visit(bd.tree, do_msb, do_lsb)

                control_deps += dv.control_deps
                data_deps += dv.data_deps

                if bd.ptr != None:
                    if isinstance(bd.ptr, df.DFIntConst) or isinstance(bd.ptr, df.DFEvalValue):
                        pass
                    else:
                        dv2 = DFDependencyVisitor(terms, binddict)
                        wv = DFDataWidthVisitor(terms, binddict)
                        width = wv.visit(bd.ptr)
                        dv2.visit(bd.ptr, width-1, 0)
                        # everything in the index is treated as control dependencies
                        control_deps += dv2.control_deps
                        control_deps += dv2.data_deps


        target_control_deps = []
        for dep in control_deps:
            found = False
            for t in target_control_deps:
                if t.name == dep.getName():
                    if t.lsb == None:
                        found = True
                    elif t.lsb == dep.lsb and t.msb == dep.msb:
                        found = True
            if not found:
                target_control_deps.append(dep.getTransRecTarget())

        target_data_deps = []
        for dep in data_deps:
            found = False
            for t in target_data_deps:
                if t.name == dep.getName():
                    if t.lsb == None:
                        found = True
                    elif t.lsb == dep.lsb and t.msb == dep.msb:
                        found = True
            if not found:
                target_data_deps.append(dep.getTransRecTarget())

        self.state.control_deps = target_merge(target_control_deps)
        self.state.data_deps = target_merge(target_data_deps)
