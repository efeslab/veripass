import os
import sys
import pathlib
import argparse
import copy
from verilator import *

from pyverilog.vparser.parser import VerilogCodeParser
from pyverilog.dataflow.modulevisitor import ModuleVisitor
from pyverilog.dataflow.signalvisitor import SignalVisitor
from pyverilog.dataflow.bindvisitor import BindVisitor
from pyverilog.utils.scope import ScopeLabel, ScopeChain
import pyverilog.dataflow.dataflow as df
import pyverilog.utils.util as util
import pyverilog.vparser.ast as vast

from utils.SingleBitOptimizationVisitor import SingleBitOptimizationVisitor
from utils.DoNothingVisitor import DoNothingVisitor

from passes.common import getConstantWidth


try:
    from gephistreamer import graph
    from gephistreamer import streamer
    GEPHISTREAMER_AVAILABLE = True
except ImportError:
    print("Failed to import gephistreamer")
    GEPHISTREAMER_AVAILABLE = False

class DFBuildAstVisitor():
    def __init__(self, terms, binddict):
        self.stack = []
        self.terms = terms
        self.binddict = binddict

    def visit(self, node):
        self.stack.append((node.__class__, node))
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        r = visitor(node)
        self.stack.pop()
        return r

    def generic_visit(self, node):
        print(node.__class__)
        assert(0)

    def visit_DFIntConst(self, node):
        value = node.value
        return vast.IntConst(str(value))

    def visit_DFEvalValue(self, node):
        value = node.eval()
        return vast.IntConst(str(node.width)+"'h"+hex(value)[2:])

    def visit_DFTerminal(self, node):
        termname = node.name
        assert(len(termname.scopechain) == 2)
        termmeta = self.terms[termname]
        if 'Rename' in termmeta.termtype:
            binds = self.binddict[termname]
            assert(len(binds) == 1)
            bd = binds[0]
            assert(bd.lsb == None and bd.msb == None and bd.ptr == None)
            return self.visit(bd.tree)
        else:
            return vast.Identifier(termname.scopechain[1].scopename)

    def visit_DFPartselect(self, node):
        lsb = self.visit(node.lsb)
        msb = self.visit(node.msb)
        var = self.visit(node.var)
        return vast.Partselect(var, msb, lsb)

    def visit_DFPointer(self, node):
        ptr = self.visit(node.ptr)
        var = self.visit(node.var)
        return vast.Pointer(var, ptr)

    def visit_DFBranch(self, node):
        condnode = self.visit(node.condnode)
        truenode = self.visit(node.truenode)
        falsenode = self.visit(node.falsenode)
        return vast.Cond(condnode, truenode, falsenode)

    def visit_DFConcat(self, node):
        items = []
        for n in node.nextnodes:
            items.append(self.visit(n))
        return vast.Concat(items)

    def visit_DFOperator(self, node):
        if node.operator == "And":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.And(a, b)
        if node.operator == "Or":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.Or(a, b)
        if node.operator == "Plus":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.Plus(a, b)
        if node.operator == "Minus":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.Minus(a, b)
        if node.operator == "Xor":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.Xor(a, b)
        if node.operator == "GreaterThan":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.GreaterThan(a, b)
        if node.operator == "GreaterEq":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.GreaterEq(a, b)
        if node.operator == "LessEq":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.LessEq(a, b)
        if node.operator == "Eq":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.Eq(a, b)
        if node.operator == "NotEq":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.NotEq(a, b)
        if node.operator == "Srl":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.Srl(a, b)
        if node.operator == "Unot":
            assert(len(node.nextnodes) == 1)
            a = self.visit(node.nextnodes[0])
            return vast.Unot(a)
        if node.operator == "LessThan":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.LessThan(a, b)

        print(node, "not implemented")
        assert(0 and "operator not implemented")


class DFDataDepVisitor:
    def __init__(self, terms, binddict):
        self.terms = terms
        self.binddict = binddict
        self.stack = []

    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        self.stack.append(node)        
        ret = visitor(node)
        self.stack.pop()
        return ret

    def generic_visit(self, node):
        items = []
        for child in node.children():
            items += self.visit(child)
        return items

    def visit_DFIntConst(self, node):
        return [TargetEntry(util.toTermname("__CONST__"), node)]

    def visit_DFTerminal(self, node):
        termname = node.name
        assert(len(termname.scopechain) == 2)
        termmeta = self.terms[termname]
        if 'Rename' in termmeta.termtype:
            binds = self.binddict[termname]
            assert(len(binds) == 1)
            bd = binds[0]
            assert(bd.lsb == None and bd.msb == None and bd.ptr == None)
            return self.visit(bd.tree)
        else:
            #print(self.stack)
            return [TargetEntry(termname, node)]

    def visit_DFPointer(self, node):
        var = self.visit(node.var)
        if len(var) != 1:
            return var
        if var[0].tree.__class__ != df.DFTerminal:
            return var
        termname = var[0].tree.name
        return [TargetEntry(termname, tree=node, ptr=node.ptr)]

    def visit_DFPartselect(self, node):
        var = self.visit(node.var)
        if len(var) != 1:
            return var
        if var[0].tree.__class__ == df.DFTerminal:
            termname = var[0].tree.name
            return [TargetEntry(termname, tree=node, msb=node.msb, lsb=node.lsb)]
        elif var[0].tree.__class__ == df.DFPointer and var[0].tree.var.__class__ == df.DFTerminal:
            termname = var[0].tree.var.name
            ptr = var[0].tree.ptr
            return [TargetEntry(termname, tree=node, msb=node.msb, lsb=node.lsb, ptr=ptr)]
        else:
            return var

    def visit_DFBranch(self, node):
        items = []
        if node.truenode != None:
            items += self.visit(node.truenode)
        if node.falsenode != None:
            items += self.visit(node.falsenode)
        return items

class DFDataWidthVisitor:
    def __init__(self, terms, binddict):
        self.terms = terms
        self.binddict = binddict
        self.stack = []

    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        self.stack.append(node)        
        ret = visitor(node)
        self.stack.pop()
        return ret

    def generic_visit(self, node):
        assert(0)

    def visit_DFTerminal(self, node):
        termname = node.name
        assert(len(termname.scopechain) == 2)
        termmeta = self.terms[termname]

        if node.fixed:
            if node.forceWidth.__class__ == int:
                return node.forceWidth
            else:
                return self.visit(node.forceWidth)
        else:
            return termmeta.msb.eval() - termmeta.lsb.eval() + 1

    def visit_DFPartselect(self, node):
        return node.msb.eval() - node.lsb.eval() + 1

    def visit_DFPointer(self, node):
        return self.visit(node.var)

    def visit_DFConcat(self, node):
        r = 0
        for n in node.nextnodes:
            r += self.visit(n)
        return r

    def visit_DFBranch(self, node):
        if node.truenode != None and node.falsenode != None:
            t = self.visit(node.truenode)
            f = self.visit(node.falsenode)
            assert(t == f)
            return t
        elif node.truenode != None:
            return self.visit(node.truenode)
        elif node.falsenode != None:
            return self.visit(node.falsenode)
        else:
            assert(0)

    def visit_DFIntConst(self, node):
        return getConstantWidth(node)

    def visit_DFEvalValue(self, node):
        return node.width

    def visit_DFOperator(self, node):
        if node.operator in {"Add", "Minus", "Or", "And", "Xor"}:
            left_width = self.visit(node.nextnodes[0])
            right_width = self.visit(node.nextnodes[1])
            assert(left_width == right_width)
            return left_width
        elif node.operator in {"Uand", "Uor"}:
            return 1
        assert(0)


class DFUnassignedCondVisitor:
    def __init__(self, terms, binddict, msb, lsb):
        self.terms = terms
        self.binddict = binddict
        self.target_msb = msb
        self.target_lsb = lsb
        self.stack = []
        self.branch_stack = []
        self.unassigned_cond = None

        assert(msb > 0 and lsb >= 0 and msb >= lsb)

    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        self.stack.append(node)        
        ret = visitor(node)
        self.stack.pop()
        return ret

    def generic_visit(self, node):
        assert(0)

    def condlist_copy_dedup(self, conds):
        new_conds = []
        for c in conds:
            exist = False
            for n in new_conds:
                if n[0] == c[0]:
                    exist = True
                    if n[1] != c[1]:
                        return "invalid condlist"
                    break
            if exist:
                continue
            else:
                new_conds.append(copy.deepcopy(c))
        return new_conds

    def build_df_condlist(self, conds):
        r = None
        for c in conds:
            tmp = c[0]
            if c[1] == False:
                tmp = df.DFOperator([tmp], "Unot")
            if r == None:
                r = tmp
            else:
                r = df.DFOperator([r, tmp], "And")
        return r

    def update_unassigned_cond(self, conds):
        if len(conds) == 0:
            return
        if self.unassigned_cond == None:
            self.unassigned_cond = self.build_df_condlist(conds)
        else:
            self.unassigned_cond = df.DFOperator(
                    [self.unassigned_cond, self.build_df_condlist(conds)],
                    "Or")
        

    def visit_DFBranch(self, node):
        self.branch_stack.append((node.condnode, True))
        true_r = None
        false_r = None
        if node.truenode != None:
            true_r = self.visit(node.truenode)
        else:
            conds_snapshot = self.condlist_copy_dedup(self.branch_stack)
            self.update_unassigned_cond(conds_snapshot)
        self.branch_stack.pop()

        self.branch_stack.append((node.condnode, False))
        if node.falsenode != None:
            false_r = self.visit(node.falsenode)
        else:
            conds_snapshot = self.condlist_copy_dedup(self.branch_stack)
            self.update_unassigned_cond(conds_snapshot)
        self.branch_stack.pop()

    def visit_DFOperator(self, node):
        return

    def visit_DFIntConst(self, node):
        return

    def visit_DFPartselect(self, node):
        part_lsb = node.lsb.eval()
        do_lsb = self.target_lsb + part_lsb
        do_msb = self.target_msb + part_lsb
        uav = DFUnassignedCondVisitor(self.terms, self.binddict, do_msb, do_lsb)
        uav.visit(node.var)
        if uav.unassigned_cond:
            self.update_unassigned_cond(
                    self.branch_stack + [(uav.unassigned_cond, True)])
        return

    def visit_DFPointer(self, node):
        # FIXME: we now assume this implies an assignment
        return

    def visit_DFTerminal(self, node):
        termname = node.name
        assert(len(termname.scopechain) == 2)
        termmeta = self.terms[termname]
        if 'Rename' in termmeta.termtype:
            binds = self.binddict[termname]
            assert(len(binds) == 1)
            bd = binds[0]
            assert(bd.lsb == None and bd.msb == None and bd.ptr == None)
            self.visit(bd.tree)

    def visit_DFConcat(self, node):
        current_conds = self.condlist_copy_dedup(self.branch_stack)
        current_lsb = 0
        interested_msb = self.target_msb
        interested_lsb = self.target_lsb
        tmp = None
        for item in reversed(node.nextnodes):
            wv = DFDataWidthVisitor(self.terms, self.binddict)
            width = wv.visit(item)
            assert(width >= 1)
            current_msb = current_lsb + width - 1
            if interested_lsb > current_msb:
                continue
            if interested_msb < current_lsb:
                continue
            do_lsb = None
            do_msb = None
            if current_msb < interested_msb:
                do_msb = current_msb
            else:
                do_msb = interested_msb
            if current_lsb > interested_lsb:
                do_lsb = current_lsb
            else:
                do_lsb = interested_lsb
            do_msb -= current_lsb
            do_lsb -= current_lsb

            uav = DFUnassignedCondVisitor(self.terms, self.binddict, do_msb, do_lsb)
            uav.visit(item)
            if uav.unassigned_cond == None:
                # If one of the sub node does not have a condition under which there's
                # no assignment, we return directly, because the target [msb:lsb] is
                # definitely assigned.
                return
            if tmp == None:
                tmp = uav.unassigned_cond
            else:
                tmp = df.DFOperator([tmp, uav.unassigned_cond], "And")
            current_lsb += width
        self.update_unassigned_cond(self.branch_stack + [(tmp, True)])














# Specify a target and a tree. Find out which part of the tree root is originated
# from the target.
class DFPerciseDataDepVisitor:
    def __init__(self, terms, binddict, target):
        self.terms = terms
        self.binddict = binddict
        self.target = target
        self.stack = []
        self.branch_stack = []

    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        self.stack.append(node)        
        ret = visitor(node)
        self.stack.pop()
        if ret[0] != None:
            if ret[1] >= ret[2]:
                visitor(node)
            assert(ret[1] < ret[2])
        return ret

    def generic_visit(self, node):
        assert(0)

    def visit_DFUndefined(self, node):
        assert(0)

    def condlist_copy_dedup(self, conds):
        new_conds = []
        for c in conds:
            exist = False
            for n in new_conds:
                if n[0] == c[0]:
                    exist = True
                    if n[1] != c[1]:
                        return "invalid condlist"
                    break
            if exist:
                continue
            else:
                new_conds.append(copy.deepcopy(c))
        return new_conds

    def visit_DFTerminal(self, node):
        termname = node.name
        assert(len(termname.scopechain) == 2)
        termmeta = self.terms[termname]
        if 'Rename' in termmeta.termtype:
            binds = self.binddict[termname]
            assert(len(binds) == 1)
            bd = binds[0]
            assert(bd.lsb == None and bd.msb == None and bd.ptr == None)
            return self.visit(bd.tree)

        if node.fixed:
            if node.forceWidth.__class__ == int:
                width = node.forceWidth
            else:
                v = DFDataWidthVisitor(self.terms, self.binddict)
                width = v.visit(node.forceWidth)
            # node.fixed is only true during x replacement
            return (None, None, width, None, None)
        else:
            width = termmeta.msb.eval() - termmeta.lsb.eval() + 1

        if termname != self.target.termname:
            return (None, None, width, None, None)

        if self.target.msb == None and self.target.lsb == None:
            condlist = self.condlist_copy_dedup(self.branch_stack)
            if condlist.__class__ == str:
                return (None, None, width, None, None)
            else:
                return (termmeta.msb.eval(), termmeta.lsb.eval(), width, condlist, None)

        assert(self.target.msb.eval() <= termmeta.msb.eval())
        assert(self.target.lsb.eval() >= termmeta.lsb.eval())

        condlist = self.condlist_copy_dedup(self.branch_stack)
        if condlist.__class__ == str:
            return (None, None, width, None, None)
        return (self.target.msb.eval(), self.target.lsb.eval(), width, condlist, None)

    def visit_DFPointer(self, node):
        var = node.var
        assert(var.__class__ == df.DFTerminal)
        ptr = node.ptr
        termname = node.var.name
        termmeta = self.terms[termname]
        width = termmeta.msb.eval() - termmeta.lsb.eval() + 1
        if termname != self.target.termname:
            return (None, None, width, None, None)

        rd_ptr = None
        if ptr != self.target.ptr:
            if ptr.__class__ != df.DFIntConst and self.target.ptr.__class__ != df.DFIntConst:
                # If control reaches here, the write ptr and read ptr are not the same and are
                # both non-constant expressions.
                # We need to return read ptr.
                rd_ptr = ptr
            elif ptr.__class__ != df.DFIntConst or self.target.ptr.__class__ != df.DFIntConst:
                # Also record here if the one of write ptr and read ptr are not constant
                rd_ptr = ptr
            else:
                return (None, None, width, None, None)
        
        r = self.visit(node.var)
        assert(r[2] == width)
        return (r[0], r[1], r[2], r[3], rd_ptr)

    def visit_DFPartselect(self, node):
        r = self.visit(node.var)
        msb = node.msb.eval()
        lsb = node.lsb.eval()
        width = msb - lsb + 1
        child_msb = r[0]
        child_lsb = r[1]

        if child_msb == None and child_lsb == None:
            return (None, None, width, None, None)

        if msb >= child_msb and child_msb >= lsb and lsb >= child_lsb:
            return (child_msb - lsb, 0, width, r[3], None)

        if child_msb >= msb and msb >= child_lsb and child_lsb >= lsb:
            return (msb - lsb, child_lsb - lsb, width, r[3], None)

        if child_msb >= msb and lsb >= child_lsb:
            return (msb - lsb, 0, width, r[3], None)

        if msb >= child_msb and child_lsb >= lsb:
            return (child_msb - lsb, child_lsb - lsb, width, r[3], None)

        return (None, None, width, None, None)

    def remove_cond_from_list(self, condlist, cond):
        new_condlist = copy.deepcopy(condlist)
        for c in new_condlist:
            if c[0] == cond:
                new_condlist.remove(c)
        return new_condlist

    def visit_DFBranch(self, node):
        self.branch_stack.append((node.condnode, True))
        true_r = None
        false_r = None
        if node.truenode != None:
            true_r = self.visit(node.truenode)
        self.branch_stack.pop()
        self.branch_stack.append((node.condnode, False))
        if node.falsenode != None:
            false_r = self.visit(node.falsenode)
        self.branch_stack.pop()
        if true_r != None and false_r != None:
            if true_r[2] != false_r[2]:
                self.visit(node.truenode)
                self.visit(node.falsenode)
            assert(true_r[2] == false_r[2])
            if true_r[0] != None and false_r[0] != None:
                # FIXME: currently only support this
                assert(true_r[0] == false_r[0])
                assert(true_r[1] == false_r[1])
                newlist = self.remove_cond_from_list(true_r[3], node.condnode)
                return (true_r[0], true_r[1], true_r[2], newlist, None)
        if true_r!= None and true_r[0] != None:
            return true_r
        elif false_r != None and false_r[0] != None:
            return false_r
        else:
            width = true_r[2] if true_r != None else false_r[2]
            return (None, None, width, None, None)

    def visit_DFConcat(self, node):
        r = []
        r_valid_cnt = 0
        width = 0
        curser = 0
        hit = {}
        for n in node.nextnodes:
            r.append(self.visit(n))
        for ent in reversed(r):
            if ent[0] != None:
                r_valid_cnt += 1
                curser = width
                hit[curser] = ent
            width += ent[2]
        if r_valid_cnt > 1:
            max_m = None
            min_l = None
            tree = None
            for key in hit:
                tree = hit[key][3]
                break
            for key in hit:
                assert(tree == hit[key][3])
                m = key + hit[key][0]
                l = key + hit[key][1]
                if max_m == None or m > max_m:
                    max_m = m
                if min_l == None or l < min_l:
                    min_l = l
            return (max_m, min_l, width, tree, None)
        elif r_valid_cnt == 1:
            return (curser + hit[curser][0], curser + hit[curser][1], width, hit[curser][3], None)
        else:
            return (None, None, width, None, None)

    def visit_DFOperator(self, node):
        if (node.operator == "And" or node.operator == "Or" or
                node.operator == "Plus" or node.operator == "Minus" or
                node.operator == "Xor"):
            r = []
            assert(len(node.nextnodes) == 2)
            for n in node.nextnodes:
                r.append(self.visit(n))
            r_valid_cnt = 0
            width = r[0][2]
            hit = []
            for ent in r:
                if ent[0] != None:
                    r_valid_cnt += 1
                    hit.append(ent)
                assert(ent[2] == width)
            if r_valid_cnt > 1:
                assert(r_valid_cnt == 2)
                assert(hit[0][3] == hit[1][3])
            if r_valid_cnt >= 1:
                return (width - 1, 0, width, hit[0][3], None)
            else:
                return (None, None, width, None, None)
        elif node.operator == "GreaterThan" or node.operator == "Eq":
            r = []
            assert(len(node.nextnodes) == 2)
            for n in node.nextnodes:
                r.append(self.visit(n))
            r_valid_cnt = 0
            hit = None
            for ent in r:
                if ent[0] != None:
                    r_valid_cnt += 1
                    hit = ent
            assert(r_valid_cnt <= 1)
            if r_valid_cnt == 1:
                return (0, 0, 1, hit[3], None)
            else:
                return (None, None, 1, None, None)
        elif node.operator == "Srl":
            assert(len(node.nextnodes) == 2)
            assert(node.nextnodes[1].__class__ == df.DFIntConst)
            sft = node.nextnodes[1].eval()
            r = self.visit(node.nextnodes[0])
            if r[0] == None:
                return (None, None, r[2], None, None)
            elif r[1] - sft >= 0:
                return (r[0] - sft, r[1] - sft, r[2], r[3], None)
            elif r[0] - sft >= 0:
                return (r[0] - sft, 0, r[2], r[3], None)
            else:
                return (None, None, r[2], None, None)
        elif node.operator == "Unot":
            assert(len(node.nextnodes) == 1)
            return self.visit(node.nextnodes[0])


        assert(0 and "operator not implemented")

    def visit_DFIntConst(self, node):
        return (None, None, node.width(), None, None)


class TargetEntry:
    def __init__(self, termname, tree=None, msb=None, lsb=None, ptr=None, rd_ptr=None,
            rd_subling=None, wr_subling=None):
        self.termname = termname
        self.msb = msb
        self.lsb = lsb
        self.ptr = ptr
        self.tree = tree
        self.rd_ptr = rd_ptr
        self.rd_subling = rd_subling
        self.wr_subling = wr_subling

    def __eq__(self, other):
        if other == None:
            return False
        if (self.termname == other.termname and
                self.msb == other.msb and
                self.lsb == other.lsb and
                self.ptr == other.ptr):
            return True
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.termname, self.msb, self.lsb, self.ptr))

    def toStr(self):
        if self.termname != util.toTermname("__CONST__"):
            return "{} {} {} {} {}".format(
                    str(self.termname),
                    str(self.msb),
                    str(self.lsb),
                    str(self.ptr),
                    str(self.rd_ptr))
        else:
            return "{} {}".format(
                    str(self.termname),
                    str(self.tree))


class RMapEntry:
    def __init__(self, dst, dst_msb, dst_lsb, dst_ptr, src, src_msb, src_lsb, src_ptr, tree, assigntype, alwaysinfo):
        self.dst = dst
        self.src = src
        self.dst_msb = dst_msb
        self.dst_lsb = dst_lsb
        self.dst_ptr = dst_ptr
        self.src_msb = src_msb
        self.src_lsb = src_lsb
        self.src_ptr = src_ptr
        self.tree = tree
        self.assigntype = assigntype
        self.alwaysinfo = alwaysinfo

class GraphNode:
    pass
    

#class ContainTargetVisitor:
#    def __init__(self, terms, binddict):
#        self.terms = terms
#        self.binddict = binddict
#        self.stack = []
#
#    def visit(self, node):
#        method = 'visit_' + node.__class__.__name__
#        visitor = getattr(self, method, self.generic_visit)
#        self.stack.append(node)        
#        ret = visitor(node)
#        self.stack.pop()
#        return ret
#
#    def generic_visit(self, node):
#        items = []
#        for child in node.children():
#            items += self.visit(child)

class FlowGuardInstrumentationPass:
    def __init__(self, ast, terms, binddict, data_in, data_in_valid, 
            data_out, reset, identifierRef, typeInfo, gephi=False,
            optimizeGen=True):
        self.ast = ast
        self.terms = terms
        self.binddict = binddict
        self.data_in = util.toTermname(data_in)
        self.data_in_valid = util.toTermname(data_in_valid)
        self.data_out = util.toTermname(data_out)
        self.reset = util.toTermname(reset)
        self.vars = []
        self.parsed = {}
        self.gephi = gephi
        if gephi and GEPHISTREAMER_AVAILABLE:
            try:
                self.stream = streamer.Streamer(streamer.GephiWS(hostname="localhost", port=8080, workspace="workspace1"))
            except:
                self.gephi = False
        self.av_cache = {}
        self.ai_cache = {}
        self.assign_cache = {}
        self.valid_cache = {}
        self.prop_cache = {}
        self.good_cache = {}
        self.instrumented_name_cache = {}
        self.instrumented_def_cache = {}
        self.blackbox_modules = {}
        self.filtered_set = set()

        self.identifierRef = identifierRef
        self.typeInfo = typeInfo

        if optimizeGen:
            self.optimizer = SingleBitOptimizationVisitor()
        else:
            self.optimizer = DoNothingVisitor()

    def addBlackboxModule(self, modulename, model):
        self.blackbox_modules[modulename] = model

    def gephi_add_node(self, n):
        if self.gephi:
            self.stream.add_node(n)

    def gephi_change_node(self, n):
        if self.gephi:
            self.stream.change_node(n)

    def gephi_delete_node(self, n):
        if self.gephi:
            self.stream.delete_node(n)

    def gephi_add_edge(self, e):
        if self.gephi:
            self.stream.add_edge(e)

    def find_prop_chain(self):
        queue = []
        queue.append(self.data_out)
        visited = set()
        reverse_map = {}

        # the first pass, from destination to source
        while len(queue) > 0:
            left = queue[0]
            queue.pop(0)
            termname = left
            visited.add(termname)
            if termname in self.binddict:

                # FIXME: verilator didn't do x propagation
                bds = self.binddict[termname]
                for bd in bds:
                    #if bd.msb != None and bd.lsb != None and bd.ptr == None:
                    #    exit()
                    v = DFDataDepVisitor(self.terms, self.binddict)
                    items = v.visit(bd.tree)
                    for itemfull in items:
                        item = itemfull.termname
                        if item == util.toTermname("__CONST__"):
                            continue
                        #print(item)
                        if not item in visited:
                            queue.append(item)
                            visited.add(item)
                        rentry = RMapEntry(termname, bd.msb, bd.lsb, bd.ptr,
                                        item, itemfull.msb, itemfull.lsb, itemfull.ptr,
                                        bd.tree, bd.parameterinfo, bd.alwaysinfo)
                        if not item in reverse_map:
                            reverse_map[item] = [rentry]
                        else:
                            exist = False
                            for re in reverse_map[item]:
                                if (rentry.dst == re.dst and
                                        rentry.dst_ptr == re.dst_ptr and
                                        rentry.dst_lsb == re.dst_lsb and
                                        rentry.dst_msb == re.dst_msb and
                                        rentry.src_ptr == re.src_ptr and
                                        rentry.src_lsb == re.src_lsb and
                                        rentry.src_msb == re.src_msb and
                                        rentry.assigntype == re.assigntype and
                                        rentry.alwaysinfo == re.alwaysinfo):
                                    exist = True
                                    break
                            if not exist:
                                reverse_map[item].append(rentry)

        # generating gephi nodes
        gephi_node_map = {}
        def getNodeByTargetEntry(target):
            target_str = target.toStr()
            if target.termname == self.data_out:
                target_str = str(self.data_out)
            if target.termname == self.data_in:
                target_str = str(self.data_in)
            if target_str in gephi_node_map:
                return gephi_node_map[target_str]
            else:
                n = graph.Node(target_str, size=10)
                gephi_node_map[target_str] = n
                n.color_hex(0, 255, 0)
                self.gephi_add_node(n)
                return n

        # the second pass, from source to destination
        visited2 = set()
        # dst -> src
        reverse_map2 = {}
        forward_map2 = {}
        target_output = []
        queue.append(TargetEntry(self.data_in))
        while len(queue) > 0:
            target = queue[0]
            queue.pop(0)
            termname = target.termname

            if target in visited2:
                continue
            visited2.add(target)

            termmeta = self.terms[termname]
            #print("--------------------------")
            #print(termname, termmeta.msb, termmeta.lsb, termmeta.dims)
            #input('')

            termnode = getNodeByTargetEntry(target)

            if termname == self.data_out:
                continue

            #print("=======================")
            #print("target:", termname, target.msb, target.lsb, target.ptr, ", target cnt:", len(reverse_map[termname]))


            rlist = []
            for itemfull in reverse_map[termname]:
                if target.ptr != None and (target.ptr.__class__ == df.DFIntConst or target.ptr.__class__ == df.DFEvalValue):
                    if itemfull.src_ptr.__class__ == df.DFTerminal:
                        # if the src ptr of the detected binding is a terminal while we target on a constant ptr, it should be counted
                        pass
                    elif itemfull.src_ptr.eval() != target.ptr.eval():
                        continue
                item = itemfull.dst
                tgt = TargetEntry(itemfull.dst, msb=itemfull.dst_msb, lsb=itemfull.dst_lsb, ptr=itemfull.dst_ptr)
                if tgt in visited2:
                    pass
                    #print("double kill!")
                    #continue

                #print("----------------------")
                #print("dst:", itemfull.dst, itemfull.dst_msb, itemfull.dst_lsb, itemfull.dst_ptr)
                #print("src:", itemfull.src, itemfull.src_msb, itemfull.src_lsb, itemfull.src_ptr)

                v = DFPerciseDataDepVisitor(self.terms, self.binddict, target)
                r = v.visit(itemfull.tree)
                r = list(r)
                if r[0] != None and itemfull.dst_lsb != None:
                    r[0] += itemfull.dst_lsb.eval()
                    r[1] += itemfull.dst_lsb.eval()

                #print(itemfull.dst, tuple(r), "added" if r[0] != None else "discarded")

                if target.rd_ptr == None and r[4] != None:
                    target.rd_ptr = r[4]
                elif target.rd_ptr != None and r[4] != None and target.rd_ptr != r[4]:
                    rd_subling = copy.deepcopy(target)
                    rd_subling.rd_ptr = r[4]
                    rd_subling.rd_subling = None
                    t = target
                    while t.rd_subling != None:
                        t = t.rd_subling
                    t.rd_subling = rd_subling

                if r[0] != None:
                    rlist.append((r, item, itemfull.dst_ptr, itemfull.assigntype, itemfull.alwaysinfo))

            def mergable(rlist):
                if len(rlist) <= 1:
                    return (False, None, None)
                base_dst = rlist[0][1]
                base_ptr = rlist[0][2]
                base_br = rlist[0][0][3]
                base_assigntype = rlist[0][3]
                base_alwaysinfo = rlist[0][4]
                min_lsb = None
                max_msb = None
                for r, dst, dst_ptr, assigntype, alwaysinfo in rlist:
                    if max_msb == None or max_msb < r[0]:
                        max_msb = r[0]
                    if min_lsb == None or min_lsb > r[1]:
                        min_lsb = r[1]
                    if dst != base_dst:
                        return (False, None, None)
                    if dst_ptr != base_ptr:
                        return (False, None, None)
                    if r[3] != base_br:
                        return (False, None, None)
                    if assigntype != base_assigntype:
                        return (False, None, None)
                    if alwaysinfo != base_alwaysinfo:
                        return (False, None, None)
                return (True, max_msb, min_lsb)

            # Whether target is assigned to a bunch of contiguous slots in an array.
            def mergable_array(rlist):
                if len(rlist) <= 1:
                    return (False, None, None)
                base_dst = rlist[0][1]
                base_ptr = rlist[0][2]
                base_br = rlist[0][0][3]
                base_assigntype = rlist[0][3]
                base_alwaysinfo = rlist[0][4]
                base_msb = rlist[0][0][0]
                base_lsb = rlist[0][0][1]
                if base_ptr == None:
                    return (False, None, None)
                wrptr_list = []
                for r, dst, dst_ptr, assigntype, alwaysinfo in rlist:
                    if dst != base_dst:
                        return (False, None, None)
                    if base_msb != r[0]:
                        return (False, None, None)
                    if base_lsb != r[1]:
                        return (False, None, None)
                    if base_br != r[3]:
                        return (False, None, None)
                    if assigntype != base_assigntype:
                        return (False, None, None)
                    if alwaysinfo != base_alwaysinfo:
                        return (False, None, None)
                    wrptr_list.append(dst_ptr)
                return (True, wrptr_list, None)

            merge_test = mergable(rlist)
            if merge_test[0] == True:
                #print("----------------------")
                #print("merge:", rlist[0])
                max_msb = merge_test[1]
                min_lsb = merge_test[2]
                r = (max_msb, min_lsb, rlist[0][0][2], rlist[0][0][3])
                rlist = [(r, rlist[0][1], rlist[0][2], rlist[0][3], rlist[0][4])]

            merge_array_test = mergable_array(rlist)
            if merge_array_test[0] == True:
                rlist = [(rlist[0][0], rlist[0][1], rlist[0][2], rlist[0][3], rlist[0][4])]

            for (r, dst, dst_ptr, assigntype, alwaysinfo) in rlist:
                if r[0] != None:
                    dst_target = TargetEntry(dst, msb=df.DFEvalValue(r[0]),
                                        lsb=df.DFEvalValue(r[1]), ptr=dst_ptr)
                    curr = dst_target
                    if merge_array_test[0] == True:
                        for i in range(1, len(merge_array_test[1])):
                            curr.wr_subling = TargetEntry(dst, msb=df.DFEvalValue(r[0]),
                                        lsb=df.DFEvalValue(r[1]), ptr=merge_array_test[1][i])
                            curr = curr.wr_subling

                    queue.append(dst_target)
                    itemnode = getNodeByTargetEntry(dst_target)
                    e = graph.Edge(termnode, itemnode)
                    self.gephi_add_edge(e)

                    # We need the reverse_map to search the src for each dst
                    if not dst_target in reverse_map2:
                        reverse_map2[dst_target] = [(target, r[3], assigntype, alwaysinfo)]
                    else:
                        need_add = True
                        for saved_src_target, saved_conds, saved_assigntype, saved_alwaysinfo in reverse_map2[dst_target]:
                            def target_eq_wptr(t1, t2):
                                if t1.rd_ptr == None or t2.rd_ptr == None:
                                    return t1 == t2
                                else:
                                    t1tmp = copy.deepcopy(t1)
                                    t2tmp = copy.deepcopy(t2)
                                    t1tmp.ptr = None
                                    t2tmp.ptr = None
                                    return t1tmp == t2tmp
                            if (target_eq_wptr(saved_src_target, target) and saved_conds == r[3] and
                                    saved_assigntype == assigntype and saved_alwaysinfo == alwaysinfo):
                                need_add = False
                        if need_add:
                            reverse_map2[dst_target].append((target, r[3], assigntype, alwaysinfo))

                    # We also need the forward_map to search the dst for each src
                    if not target in forward_map2:
                        forward_map2[target] = [(dst_target, r[3], assigntype, alwaysinfo)]
                    else:
                        need_add = True
                        for saved_dst_target, saved_conds, saved_assigntype, saved_alwaysinfo in forward_map2[target]:
                            if (saved_dst_target == target and saved_conds == r[3] and
                                    saved_assigntype == assigntype and saved_alwaysinfo):
                                need_add = False
                        if need_add:
                            forward_map2[target].append((dst_target, r[3], assigntype, alwaysinfo))

                    if dst == self.data_out:
                        target_output.append(dst_target)

        prop_chain = {}
        for tg in target_output:
            assert(not tg in queue)
            queue.append(tg)
        while len(queue) > 0:
            dst = queue[0]
            queue.pop(0)

            if dst in prop_chain:
                continue
            prop_chain[dst] = []

            if dst.termname == self.data_in:
                continue

            for src, conds, assigntype, alwaysinfo in reverse_map2[dst]:
                queue.append(src)

        unassigned_map2 = {}
        # Till now, reverse_map2 contains the reverse mapping for all nodes from to which the destination is
        # reachable. We need to add the nodes that directly connect to any nodes in the propagation chain.
        for node in prop_chain:
            if node.termname == self.data_in:
                continue

            interested_lsb = None
            interested_msb = None
            if node.lsb == None:
                interested_lsb = self.terms[termname].lsb.eval()
            else:
                interested_lsb = node.lsb.eval()
            if node.msb == None:
                interested_msb = self.terms[termname].msb.eval()
            else:
                interested_msb = node.msb.eval()
            termname = node.termname
            bds = self.binddict[termname]
            for bd in bds:
                bd_lsb = None
                if bd.lsb == None:
                    bd_lsb = self.terms[termname].lsb.eval()
                else:
                    bd_lsb = bd.lsb.eval()
                bd_msb = None
                if bd.msb == None:
                    bd_msb  = self.terms[termname].msb.eval()
                else:
                    bd_msb = bd.msb.eval()
                if bd_lsb > interested_msb:
                    continue
                if bd_msb < interested_lsb:
                    continue
                do_msb = None
                do_lsb = None
                if bd_msb < interested_msb:
                    do_msb = bd_msb
                else:
                    do_msb = interested_msb
                if bd_lsb > interested_lsb:
                    do_lsb = bd_lsb
                else:
                    do_lsb = interested_lsb
                do_lsb -= bd_lsb
                do_msb -= bd_lsb
                uav = DFUnassignedCondVisitor(self.terms, self.binddict, do_msb, do_lsb)
                uav.visit(bd.tree)
                #print(uav.unassigned_cond, "-->", termname, interested_msb, interested_lsb, bd_msb, bd_lsb)

                if not node.termname in unassigned_map2:
                    unassigned_map2[node.termname] = []
                unassigned_map2[node.termname].append((bd, uav.unassigned_cond))

        dff_map = {}
        for n in prop_chain:
            if not n in reverse_map2:
                continue
            for src, conds, assigntype, alwaysinfo in reverse_map2[n]:
                if assigntype == "nonblocking":
                    dff_map[n] = alwaysinfo

        for node in prop_chain:
            #print(node.toStr())
            n = getNodeByTargetEntry(node)
            n.color_hex(255, 0, 0)
            self.gephi_change_node(n)

        for node in dff_map:
            n = getNodeByTargetEntry(node)
            n.color_hex(0, 255, 255)
            self.gephi_change_node(n)

        for node in visited2:
            if not node in prop_chain:
                n = getNodeByTargetEntry(node)
                self.gephi_delete_node(n)

        start = getNodeByTargetEntry(TargetEntry(self.data_in))
        start.color_hex(0, 0, 255)
        start.property["size"] = 25
        self.gephi_change_node(start)
        end = getNodeByTargetEntry(TargetEntry(self.data_out))
        end.color_hex(0, 0, 255)
        end.property["size"] = 25
        self.gephi_change_node(end)


        return (prop_chain, reverse_map2, forward_map2, unassigned_map2)

    def get_merged_conds(self, conds):
        if len(conds) == 0:
            return vast.IntConst("1'b1")
        
        builder = DFBuildAstVisitor(self.terms, self.binddict)
        base = builder.visit(conds[0][0])
        if conds[0][1] == False:
            base = vast.Unot(base)
        i = 1
        while i < len(conds):
            r = builder.visit(conds[i][0])
            if conds[i][1] == False:
                r = vast.Unot(r)
            base = vast.And(base, r)
            i += 1
        return base

    def get_instrumented_name(self, target, ntype):
        if (target, ntype) in self.instrumented_name_cache:
            return self.instrumented_name_cache[(target, ntype)]

        term = self.terms[target.termname]
        name = str(target.termname[1])
        if target.lsb != None:
            assert(target.msb != None)
            lsb = target.lsb.eval()
            msb = target.msb.eval()
            name += "__BRA__" + str(msb) + "__03A" + str(lsb) + "__KET__"
        name += "__" + ntype.upper() + "__"

        if target.ptr == None:
            #assert(term.dims == None)
            r = vast.Identifier(name)
            self.instrumented_name_cache[(target, ntype)] = r
            return r
        else:
            assert(term.dims != None)
            builder = DFBuildAstVisitor(self.terms, self.binddict)
            r = vast.Pointer(vast.Identifier(name), builder.visit(target.ptr))
            self.instrumented_name_cache[(target, ntype)] = r
            return r

    def get_instrumented_def(self, target, ntype):
        term = self.terms[target.termname]
        name = str(target.termname[1])
        if target.lsb != None:
            assert(target.msb != None)
            lsb = target.lsb.eval()
            msb = target.msb.eval()
            name += "__BRA__" + str(msb) + "__03A" + str(lsb) + "__KET__"
        name += "__" + ntype.upper() + "__"

        if name in self.instrumented_def_cache:
            return None

        if target.ptr == None:
            r = vast.Logic(name)
        else:
            term = self.terms[target.termname]
            assert(len(term.dims) == 1)
            dim_msb = term.dims[0][0].eval()
            dim_lsb = term.dims[0][1].eval()
            width = vast.Width(vast.IntConst(str(dim_msb)), vast.IntConst(str(dim_lsb)))
            dims = vast.Dimensions([width])
            r = vast.Logic(name, dimensions=dims)

        self.instrumented_def_cache[name] = r
        return r

    def get_av_name(self, target):
        return self.get_instrumented_name(target, "av")

    def get_av_def(self, target):
        return self.get_instrumented_def(target, "av")

    def get_av_q_name(self, target):
        return self.get_instrumented_name(target, "av_q")

    def get_av_q_def(self, target):
        return self.get_instrumented_def(target, "av_q")

    def get_ai_name(self, target):
        return self.get_instrumented_name(target, "ai")

    def get_ai_def(self, target):
        return self.get_instrumented_def(target, "ai")

    def get_ai_q_name(self, target):
        return self.get_instrumented_name(target, "ai_q")

    def get_ai_q_def(self, target):
        return self.get_instrumented_def(target, "ai_q")

    def get_valid_name(self, target):
        return self.get_instrumented_name(target, "valid")

    def get_valid_def(self, target):
        return self.get_instrumented_def(target, "valid")

    def get_valid_q_name(self, target):
        return self.get_instrumented_name(target, "valid_q")

    def get_valid_q_def(self, target):
        return self.get_instrumented_def(target, "valid_q")

    def get_prop_name(self, target):
        return self.get_instrumented_name(target, "prop")

    def get_prop_def(self, target):
        return self.get_instrumented_def(target, "prop")

    def get_prop_q_name(self, target):
        return self.get_instrumented_name(target, "prop_q")

    def get_prop_q_def(self, target):
        return self.get_instrumented_def(target, "prop_q")

    def get_assign_name(self, target):
        return self.get_instrumented_name(target, "assign")

    def get_assign_def(self, target):
        return self.get_instrumented_def(target, "assign")

    def get_assign_q_name(self, target):
        return self.get_instrumented_name(target, "assign_q")

    def get_assign_q_def(self, target):
        return self.get_instrumented_def(target, "assign_q")

    def get_good_name(self, target):
        return self.get_instrumented_name(target, "good")

    def get_good_def(self, target):
        return self.get_instrumented_def(target, "good")

    def get_good_q_name(self, target):
        return self.get_instrumented_name(target, "good_q")

    def get_good_q_def(self, target):
        return self.get_instrumented_def(target, "good_q")

    # based on section 5.1 equation 1
    def get_av(self, target, reverse_map):
        if target in self.av_cache:
            return self.av_cache[target]

        base = None
        for src, conds, assigntype, alwaysinfo in reverse_map[target]:
            sigma = self.get_merged_conds(conds)
            src_av = None
            if src.rd_ptr == None:
                src_av = vast.And(sigma, self.get_valid_name(src))
            else:
                # FIXME: There're a bunch of corner case not considered
                t = src
                v = None
                while t != None:
                    tmp = copy.deepcopy(t)
                    tmp.ptr = tmp.rd_ptr
                    tmp.rd_subling = None
                    if v == None:
                        v = self.get_valid_name(tmp)
                    else:
                        v = vast.Or(v, self.get_valid_name(tmp))
                    t = t.rd_subling
                src_av = vast.And(sigma, v)

            if base == None:
                base = src_av
            else:
                base = vast.Or(base, src_av)

        self.av_cache[target] = base
        return self.optimizer.visit(base)

    def get_av_q(self, target):
        return self.get_av_name(target)

    # based on section 5.1 equation 2
    def get_ai(self, target, reverse_map, idx_override=None):
        tgt = copy.deepcopy(target)
        if idx_override != None:
            tgt.ptr = idx_override

        if tgt in self.ai_cache:
            return self.ai_cache[tgt]

        r = vast.And(
                self.get_assign_name(tgt),
                vast.Unot(self.get_av_name(tgt)));

        self.ai_cache[tgt] = r
        return self.optimizer.visit(r)

    def get_ai_q(self, target):
        return self.get_ai_name(target)

    ## based on section 5.1 equation 3
    #def get_assign(self, target, reverse_map):
    #    if target in self.assign_cache:
    #        return self.assign_cache[target]

    #    base = None
    #    for src, conds, assigntype, alwaysinfo in reverse_map[target]:
    #        sigma = self.get_merged_conds(conds)
    #        if base == None:
    #            base = sigma
    #        else:
    #            base = vast.Or(base, sigma)

    #    self.assign_cache[target] = base
    #    return base

    # Based on section 5.1 equation 3. However, we didn't maintain the propagation
    # relationship for all variables, instead, we maintain the condition under which
    # a variable in the propagation chain is not assigned.
    def get_assign(self, target, unassigned_map):
        if target in self.assign_cache:
            return self.assign_cache[target]

        interested_lsb = None
        interested_msb = None
        interested_ptr = None
        if target.lsb == None:
            interested_lsb = self.terms[target.termname].lsb.eval()
        else:
            interested_lsb = target.lsb.eval()
        if target.msb == None:
            interested_msb = self.terms[target.termname].msb.eval()
        else:
            interested_msb = target.msb.eval()
        interested_ptr = target.ptr

        builder = DFBuildAstVisitor(self.terms, self.binddict)

        base = None
        interested_bds = []
        for bd, unassigned_cond in unassigned_map[target.termname]:
            bd_lsb = None
            if bd.lsb == None:
                bd_lsb = self.terms[target.termname].lsb.eval()
            else:
                bd_lsb = bd.lsb.eval()
            bd_msb = None
            if bd.msb == None:
                bd_msb  = self.terms[target.termname].msb.eval()
            else:
                bd_msb = bd.msb.eval()

            if bd_lsb > interested_msb:
                continue
            if bd_msb < interested_lsb:
                continue

            addon = None
            if bd.ptr == None:
                assert(interested_ptr == None)
                interested_bds.append((bd, unassigned_cond, addon))
            elif not isinstance(bd.ptr, df.DFIntConst) and not isinstance(bd.ptr, df.DFEvalValue):
                addon = vast.Eq(builder.visit(interested_ptr), builder.visit(bd.ptr))
                interested_bds.append((bd, unassigned_cond, addon))
            elif bd.ptr.eval() == interested_ptr.eval():
                interested_bds.append((bd, unassigned_cond, addon))

        l = []
        for bd, unassigned_cond, addon in interested_bds:
            if unassigned_cond == None:
                continue
            tmp = None
            if addon == None:
                tmp = vast.Unot(builder.visit(unassigned_cond))
            else:
                tmp = vast.And(
                        vast.Unot(builder.visit(unassigned_cond)),
                        addon)
            existed = False
            for ent in l:
                if ent == tmp:
                    existed = True
            if not existed:
                l.append(tmp)

        r = None
        for ent in l:
            if r == None:
                r = ent
            else:
                r = vast.Or(r, ent)

        if r == None:
            r = vast.IntConst("1'b1")
        return self.optimizer.visit(r)

    def get_assign_q(self, target):
        return self.get_assign_name(target)

    # based on section 5.1 equation 4
    def get_valid(self, target, prop_chain, reverse_map, wire=False, idx_override=None):
        tgt = copy.deepcopy(target)
        if idx_override != None:
            tgt.ptr = idx_override

        if tgt in self.valid_cache:
            return self.valid_cache[tgt]

        if target in prop_chain:
            if wire:
                r = self.get_av_name(tgt)
            else:
                r = vast.Or(self.get_av_q_name(tgt),
                        vast.And(vast.Unot(self.get_assign_q_name(tgt)),
                            self.get_valid_q_name(tgt)))
        else:
            # return False if target not in prop_chain
            r = vast.IntConst("1'b0")

        self.valid_cache[tgt] = r
        return self.optimizer.visit(r)

    def get_valid_q(self, target):
        return self.get_valid_name(target)

    # based on section 5.1 equation 5
    def get_prop(self, target, prop_chain, forward_map, dff_map):
        if target in self.prop_cache:
            return self.prop_cache[target]

        assert(target in dff_map)
        rlist = []
        builder = DFBuildAstVisitor(self.terms, self.binddict)
        for dst, conds, assigntype, alwaysinfo in forward_map[target]:
            if dst.ptr != None:
                varname = str(dst.termname[1])
                varref = self.identifierRef[varname]
                vartype = self.typeInfo[varref]
                assert(len(vartype.dimensions) == 1)
                rlist.append((dst, vast.And(
                    self.get_merged_conds(conds),
                    vast.LessThan(builder.visit(dst.ptr), vast.IntConst(
                        str(vartype.dimensions[0].bit_length())+"'h"+hex(vartype.dimensions[0])[2:]))
                    )))
                print("++++", dst.termname)
            else:
                rlist.append((dst, self.get_merged_conds(conds)))
        rlist_changed = True

        # the dst may not be a register, so we get the corresponding register
        while rlist_changed:
            dst, conds = rlist[0]
            rlist.pop(0)
            if dst in dff_map or dst.termname == self.data_out:
                rlist.append((dst, conds))
                rlist_changed = False
            else:
                if not dst in prop_chain:
                    # If the dst is not in prop_chain, it means dst is not in the prop chain,
                    # according to section 5.2, this dst is ignored.
                    # As a result, dst will be removed and no new entry will be appended. We can
                    # safely set rlist_changed to False.
                    rlist_changed = False
                    continue
                for ndst, ndst_conds, assigntype, alwaysinfo in forward_map[dst]:
                    print("adding", ndst.toStr())
                    if ndst.ptr != None:
                        varname = str(ndst.termname[1])
                        varref = self.identifierRef[varname]
                        vartype = self.typeInfo[varref]
                        assert(len(vartype.dimensions) == 1)
                        rlist.append((ndst, vast.And(conds, vast.And(
                            self.get_merged_conds(ndst_conds),
                            vast.LessThan(builder.visit(dst.ptr), vast.IntConst(
                                str(vartype.dimensions[0].bit_length())+"'h"+hex(vartype.dimensions[0])[2:]))
                            ))))
                        print("++++", ndst.termname)
                    else:
                        rlist.append((ndst, vast.And(conds, self.get_merged_conds(ndst_conds))))
                rlist_changed = True

        base = None
        for dst, conds in rlist:
            if base == None:
                base = conds
            else:
                if base != conds:
                    base = vast.Or(base, conds)

        self.prop_cache[target] = base
        return self.optimizer.visit(base)

    def get_prop_q(self, target):
        return self.get_prop_name(target)

    def get_good(self, target, idx_override=None):
        tgt = copy.deepcopy(target)
        if idx_override != None:
            tgt.ptr = idx_override

        if tgt in self.good_cache:
            return self.good_cache[tgt]

        builder = DFBuildAstVisitor(self.terms, self.binddict)
        r = vast.Cond(vast.Or(builder.visit(df.DFTerminal(self.reset)), self.get_ai_q_name(tgt)), vast.IntConst("1'b1"),
                vast.Cond(self.get_av_q_name(tgt), vast.IntConst("1'b0"),
                    vast.Or(self.get_good_q_name(tgt), self.get_prop_q_name(tgt))))

        self.good_cache[tgt] = r
        return self.optimizer.visit(r)

    def get_check(self, target, prop_chain, forward_map, dff_map, idx_override=None):
        tgt = copy.deepcopy(target)
        if idx_override != None:
            tgt.ptr = idx_override

        # We can skip checking if the source always propagates
        prop_val = self.get_prop(tgt, prop_chain, forward_map, dff_map)
        if isinstance(prop_val, vast.IntConst) and prop_val.value == "1'b1":
            return None

        r = vast.IfStatement(vast.And(
                    vast.Unot(vast.Or(self.get_good_q_name(tgt), self.get_prop_q_name(tgt))),
                    self.get_assign_q_name(tgt)),
                vast.SingleStatement(vast.SystemCall("display", [
                    vast.StringConst("[%0t] %%loss: " + target.toStr()),
                    vast.SystemCall("time", [])
                ])),
                None)

        return r

    def get_good_q(self, target):
        return self.get_good_name(target)

    def instrument(self):
        prop_chain, reverse_map, forward_map, unassigned_map = self.find_prop_chain()
        print()

        ldefs = []
        linsts = []
        lblocking = []
        lnonblocking = {}
        vast_builder = DFBuildAstVisitor(self.terms, self.binddict)

        # dff_map contains all dffs in the "propagation chain", which is the actually
        # propagation chain mentioned in the paper
        dff_map = {}
        # m_in and m_out are the signals that connect to an input or output port of
        # a blackbox module, they need to have some spacial handling as mentioned in
        # section 5.2
        m_in = set()
        m_out = set()
        for n in prop_chain:
            if not n in reverse_map:
                continue
            for src, conds, assigntype, alwaysinfo in reverse_map[n]:
                if assigntype == "nonblocking":
                    dff_map[n] = alwaysinfo
                if assigntype in self.blackbox_modules:
                    print(assigntype, n.toStr())
                    m_in.add(src)
                    m_out.add(n)
                    # For convience, we consider these inputs and outputs as dffs; however,
                    # they don't have alwaysinfos
                    dff_map[n] = None
                    dff_map[src] = None

        for n in prop_chain:
            if not n in reverse_map:
                continue
            if n in dff_map:
                print(n.toStr())
            else:
                print("-", n.toStr())

        array_instrumented = set()
        for n in prop_chain:
            if not n in reverse_map:
                continue

            if (n.ptr != None and n.ptr.__class__ != df.DFIntConst and n.ptr.__class__ != df.DFEvalValue):
                if n.termname in array_instrumented:
                    print("yyyy", n.termname, n.ptr)
                    continue
                array_instrumented.add(n.termname)

            ldefs.append(self.get_av_def(n))
            ldefs.append(self.get_ai_def(n))
            ldefs.append(self.get_assign_def(n))
            ldefs.append(self.get_valid_def(n))

            # If n is a blackbox module output, the generation of assignments to
            # these signals will be handled by the model of that module, so we can
            # skip this stage.
            # However, we should still generate the rest of definition of these sigs
            if n in m_out:
                ldefs.append(self.get_av_q_def(n))
                ldefs.append(self.get_ai_q_def(n))
                ldefs.append(self.get_assign_q_def(n))
                ldefs.append(self.get_valid_q_def(n))
                continue

            src, conds, assigntype, alwaysinfo = reverse_map[n][0]

            # for nonblocking assignments, we need to generate the _q signal
            if assigntype == "nonblocking":
                senslist = (alwaysinfo.original_senslist, alwaysinfo.clock_name, alwaysinfo.clock_edge)

                ldefs.append(self.get_av_q_def(n))
                ldefs.append(self.get_ai_q_def(n))
                ldefs.append(self.get_assign_q_def(n))
                ldefs.append(self.get_valid_q_def(n))

                if not senslist in lnonblocking:
                    lnonblocking[senslist] = []


                if (n.ptr != None and n.ptr.__class__ != df.DFIntConst and n.ptr.__class__ != df.DFEvalValue):
                    term = self.terms[n.termname]
                    print("::::", n.toStr(), "::::", term.dims)
                    dim = term.dims[0][0].eval() - term.dims[0][1].eval() + 1
                    index_builder = DFBuildAstVisitor(self.terms, self.binddict)
                    access_ptr = n.ptr if n.rd_ptr == None else n.rd_ptr
                    access_ptr_width = DFDataWidthVisitor(self.terms, self.binddict).visit(access_ptr)
                    width_prefix = str(access_ptr_width) + "'h"
                    for i in range(0, dim):
                        tmpn = copy.deepcopy(n)
                        tmpn.ptr = df.DFIntConst(width_prefix+hex(i)[2:])
                        lnonblocking[senslist].append(vast.NonblockingSubstitution(
                            vast.Lvalue(self.get_av_q_name(tmpn)),
                            vast.Rvalue(self.get_av_q(tmpn))))
                        lnonblocking[senslist].append(vast.NonblockingSubstitution(
                            vast.Lvalue(self.get_ai_q_name(tmpn)),
                            vast.Rvalue(self.get_ai_q(tmpn))))
                        lnonblocking[senslist].append(vast.NonblockingSubstitution(
                            vast.Lvalue(self.get_assign_q_name(tmpn)),
                            vast.Rvalue(self.get_assign_q(tmpn))))
                        lnonblocking[senslist].append(vast.NonblockingSubstitution(
                            vast.Lvalue(self.get_valid_q_name(tmpn)),
                            vast.Rvalue(self.get_valid_q(tmpn))))
                else:
                    lnonblocking[senslist].append(vast.NonblockingSubstitution(
                        vast.Lvalue(self.get_av_q_name(n)),
                        vast.Rvalue(self.get_av_q(n))))
                    lnonblocking[senslist].append(vast.NonblockingSubstitution(
                        vast.Lvalue(self.get_ai_q_name(n)),
                        vast.Rvalue(self.get_ai_q(n))))
                    lnonblocking[senslist].append(vast.NonblockingSubstitution(
                        vast.Lvalue(self.get_assign_q_name(n)),
                        vast.Rvalue(self.get_assign_q(n))))
                    lnonblocking[senslist].append(vast.NonblockingSubstitution(
                        vast.Lvalue(self.get_valid_q_name(n)),
                        vast.Rvalue(self.get_valid_q(n))))

            wire = not assigntype == "nonblocking"

            if (n.ptr != None and n.ptr.__class__ != df.DFIntConst and n.ptr.__class__ != df.DFEvalValue):
                term = self.terms[n.termname]
                print("::::", n.toStr(), "::::", term.dims)
                dim = term.dims[0][0].eval() - term.dims[0][1].eval() + 1
                index_builder = DFBuildAstVisitor(self.terms, self.binddict)
                access_ptr = n.ptr
                access_ptr_width = DFDataWidthVisitor(self.terms, self.binddict).visit(access_ptr)
                width_prefix = str(access_ptr_width) + "'h"

                for i in range(0, dim):
                    tmpn = copy.deepcopy(n)
                    tmpn.ptr = df.DFIntConst(width_prefix+hex(i)[2:])
                    if n.wr_subling == None:
                        lblocking.append(vast.Assign(
                            vast.Lvalue(self.get_av_name(tmpn)),
                            vast.Rvalue(vast.And(
                                vast.Eq(vast.IntConst(width_prefix+hex(i)[2:]), index_builder.visit(access_ptr)),
                                self.get_av(n, reverse_map)))))
                    else:
                        # FIXME: this is actually a pretty dangerous hack...
                        curr = n
                        idx_match = None
                        while curr != None:
                            if idx_match == None:
                                idx_match = vast.Eq(vast.IntConst(width_prefix+hex(i)[2:]), index_builder.visit(curr.ptr))
                            else:
                                idx_match = vast.Or(idx_match,
                                        vast.Eq(vast.IntConst(width_prefix+hex(i)[2:]), index_builder.visit(curr.ptr)))
                            curr = curr.wr_subling
                        lblocking.append(vast.Assign(
                            vast.Lvalue(self.get_av_name(tmpn)),
                            vast.Rvalue(vast.And(idx_match, self.get_av(n, reverse_map)))))
                    lblocking.append(vast.Assign(
                        vast.Lvalue(self.get_ai_name(tmpn)),
                        vast.Rvalue(self.get_ai(n, reverse_map, idx_override=tmpn.ptr))))
                    lblocking.append(vast.Assign(
                        vast.Lvalue(self.get_assign_name(tmpn)),
                        vast.Rvalue(self.get_assign(tmpn, unassigned_map))))
                    lblocking.append(vast.Assign(
                        vast.Lvalue(self.get_valid_name(tmpn)),
                        vast.Rvalue(self.get_valid(n, prop_chain, reverse_map, wire, idx_override=tmpn.ptr))))
            else:
                # for all assignments, the _assign, _ai, and _av are in the same cycle
                lblocking.append(vast.Assign(
                    vast.Lvalue(self.get_av_name(n)),
                    vast.Rvalue(self.get_av(n, reverse_map))))
                lblocking.append(vast.Assign(
                    vast.Lvalue(self.get_ai_name(n)),
                    vast.Rvalue(self.get_ai(n, reverse_map))))
                lblocking.append(vast.Assign(
                    vast.Lvalue(self.get_assign_name(n)),
                    vast.Rvalue(self.get_assign(n, unassigned_map))))
                lblocking.append(vast.Assign(
                    vast.Lvalue(self.get_valid_name(n)),
                    vast.Rvalue(self.get_valid(n, prop_chain, reverse_map, wire))))

        array_instrumented = set()
        for n in dff_map:
            ldefs.append(self.get_prop_def(n))
            ldefs.append(self.get_prop_q_def(n))
            ldefs.append(self.get_good_def(n))
            ldefs.append(self.get_good_q_def(n))

            if (n.ptr != None and n.ptr.__class__ != df.DFIntConst and n.ptr.__class__ != df.DFEvalValue):
                if n.termname in array_instrumented:
                    print("zzzz", n.termname, n.ptr)
                array_instrumented.add(n.termname)

            # If n is an input port of a blackbox module, the generation of prop
            # signal will be handled by the model of the module. So skip here.
            if n in m_in:
                continue

            # Although we put everything in m_in and m_out into dff_map, they should
            # be skipped here because the signals for m_out should be generated by
            # the model, and the signal for m_in does not make sense.
            if n in m_out:
                continue

            dst, conds, assigntype, alwaysinfo = reverse_map[n][0]
            if alwaysinfo == None:
                assert(0)
            senslist = (alwaysinfo.original_senslist, alwaysinfo.clock_name, alwaysinfo.clock_edge)

            if not senslist in lnonblocking:
                lnonblocking[senslist] = []

            if (n.ptr != None and n.ptr.__class__ != df.DFIntConst and n.ptr.__class__ != df.DFEvalValue):
                term = self.terms[n.termname]
                print("::::", n.toStr(), "::::", term.dims)
                dim = term.dims[0][0].eval() - term.dims[0][1].eval() + 1
                index_builder = DFBuildAstVisitor(self.terms, self.binddict)

                if n.rd_subling == None:
                    access_ptr = n.ptr if n.rd_ptr == None else n.rd_ptr
                    access_ptr_width = DFDataWidthVisitor(self.terms, self.binddict).visit(access_ptr)
                    width_prefix = str(access_ptr_width) + "'h"
                    for i in range(0, dim):
                        tmpn = copy.deepcopy(n)
                        tmpn.ptr = df.DFIntConst(width_prefix+hex(i)[2:])
                        lnonblocking[senslist].append(vast.NonblockingSubstitution(
                            vast.Lvalue(self.get_prop_q_name(tmpn)),
                            vast.Rvalue(self.get_prop_q(tmpn))))
                        prop_val = vast.And(
                                    vast.Eq(vast.IntConst(width_prefix+hex(i)[2:]), index_builder.visit(access_ptr)),
                                    self.get_prop(n, prop_chain, forward_map, dff_map))
                        self.prop_cache[tmpn] = prop_val
                        lblocking.append(vast.Assign(
                            vast.Lvalue(self.get_prop_name(tmpn)),
                            vast.Rvalue(prop_val)))

                        lnonblocking[senslist].append(vast.NonblockingSubstitution(
                            vast.Lvalue(self.get_good_q_name(tmpn)),
                            vast.Rvalue(self.get_good_q(tmpn))))
                        lblocking.append(vast.Assign(
                            vast.Lvalue(self.get_good_name(tmpn)),
                            vast.Rvalue(self.get_good(tmpn))))

                        if not self.check_filtered(tmpn.termname):
                            check_logic = self.get_check(tmpn, prop_chain, forward_map, dff_map)
                            if check_logic:
                                lnonblocking[senslist].append(check_logic)
                else:
                    t = n
                    i = 0
                    while t != None:
                        access_ptr = t.rd_ptr
                        assert(access_ptr.__class__ == df.DFIntConst or
                                access_ptr.__class__ == df.DFEvalValue)

                        tmpn = copy.deepcopy(n)
                        tmpn.ptr = t.rd_ptr
                        tmpn.rd_subling = None
                        lnonblocking[senslist].append(vast.NonblockingSubstitution(
                            vast.Lvalue(self.get_prop_q_name(tmpn)),
                            vast.Rvalue(self.get_prop_q(tmpn))))

                        # FIXME: here's a bunch of hack...
                        prop_val = self.get_prop(n, prop_chain, forward_map, dff_map)
                        self.prop_cache[tmpn] = prop_val
                        lblocking.append(vast.Assign(
                            vast.Lvalue(self.get_prop_name(tmpn)),
                            vast.Rvalue(prop_val)))

                        lnonblocking[senslist].append(vast.NonblockingSubstitution(
                            vast.Lvalue(self.get_good_q_name(tmpn)),
                            vast.Rvalue(self.get_good_q(tmpn))))
                        lblocking.append(vast.Assign(
                            vast.Lvalue(self.get_good_name(tmpn)),
                            vast.Rvalue(self.get_good(tmpn))))

                        if not self.check_filtered(tmpn.termname):
                            check_logic = self.get_check(tmpn, prop_chain, forward_map, dff_map)
                            if check_logic:
                                lnonblocking[senslist].append(check_logic)

                        t = t.rd_subling
                        i += 1
                    assert(i == dim)

            else:
                lnonblocking[senslist].append(vast.NonblockingSubstitution(
                    vast.Lvalue(self.get_prop_q_name(n)),
                    vast.Rvalue(self.get_prop_q(n))))
                lblocking.append(vast.Assign(
                    vast.Lvalue(self.get_prop_name(n)),
                    vast.Rvalue(self.get_prop(n, prop_chain, forward_map, dff_map))))

                lnonblocking[senslist].append(vast.NonblockingSubstitution(
                    vast.Lvalue(self.get_good_q_name(n)),
                    vast.Rvalue(self.get_good_q(n))))
                lblocking.append(vast.Assign(
                    vast.Lvalue(self.get_good_name(n)),
                    vast.Rvalue(self.get_good(n))))

                if not self.check_filtered(n.termname):
                    check_logic = self.get_check(n, prop_chain, forward_map, dff_map)
                    if check_logic:
                        lnonblocking[senslist].append(check_logic)

        for n in m_in:
            for bbm in self.blackbox_modules:
                r = None
                r = self.blackbox_modules[bbm].instrument(self, n)
                if len(r) != 0:
                    linsts += r

        for n in m_out:
            for bbm in self.blackbox_modules:
                r = None
                r = self.blackbox_modules[bbm].instrument(self, n)
                if len(r) != 0:
                    linsts += r

        # generate the valid signal for the input
        ldefs.append(self.get_valid_def(TargetEntry(self.data_in)))
        lblocking.append(vast.Assign(
            vast.Lvalue(self.get_valid_name(TargetEntry(self.data_in))),
            vast.Rvalue(vast.Identifier(str(self.data_in_valid[1])))))

        ldefs_notnone = []
        for d in ldefs:
            if d != None:
                ldefs_notnone.append(d)

        self.ast.items += ldefs_notnone
        self.ast.items += linsts
        self.ast.items += lblocking
        for senslist in lnonblocking:
            slist = vast.SensList([vast.Sens(vast.Identifier(str(senslist[1][1])), type=senslist[2])])
            self.ast.items.append(vast.Always(
                    slist,
                    vast.Block(lnonblocking[senslist])))

    def set_filtered(self, fl):
        with open(fl, "r") as f:
            log = f.read()
        log = log.splitlines()
        for l in log:
            l = l.split()
            assert(len(l) == 3)
            print(l)
            self.filtered_set.add(util.toTermname(l[0]))
        print(self.filtered_set)

    def check_filtered(self, node):
        assert(isinstance(node, ScopeChain))
        return node in self.filtered_set
