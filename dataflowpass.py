import os
import sys
import pathlib
import argparse
import copy
from verilator import *
from recordpass import *

from pyverilog.vparser.parser import VerilogCodeParser
from pyverilog.dataflow.modulevisitor import ModuleVisitor
from pyverilog.dataflow.signalvisitor import SignalVisitor
from pyverilog.dataflow.bindvisitor import BindVisitor
import pyverilog.dataflow.dataflow as df
import pyverilog.utils.util as util
import pyverilog.vparser.ast as vast

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
        assert(0)

    def visit_DFIntConst(self, node):
        value = node.eval()
        return vast.IntConst(str(value))

    def visit_DFEvalValue(self, node):
        value = node.eval()
        return vast.IntConst(str(value))

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
        if node.operator == "Srl":
            assert(len(node.nextnodes) == 2)
            a = self.visit(node.nextnodes[0])
            b = self.visit(node.nextnodes[1])
            return vast.Srl(a, b)
        if node.operator == "Unot":
            assert(len(node.nextnodes) == 1)
            a = self.visit(node.nextnodes[0])
            return vast.Unot(a)
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
            if node.forceWidth.__name__ == int:
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
                pass
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
    def __init__(self, termname, tree=None, msb=None, lsb=None, ptr=None, rd_ptr=None):
        self.termname = termname
        self.msb = msb
        self.lsb = lsb
        self.ptr = ptr
        self.tree = tree
        self.rd_ptr = rd_ptr

    def __eq__(self, other):
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
        return "{} {} {} {} {}".format(
                str(self.termname),
                str(self.msb),
                str(self.lsb),
                str(self.ptr),
                str(self.rd_ptr))


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

class dataflowtest:
    def __init__(self, ast, terms, binddict, data_in, data_in_valid, data_out, reset, gephi=True):
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
                if termname == util.toTermname("ccip_std_afu_wrapper.ccip_std_afu__DOT__mpf__DOT__mpf_edge_fiu__DOT__wr_heap_data__DOT__mem_rd1__0281__029"):
                    print("fuck")

                # FIXME: verilator didn't do x propagation
                bds = self.binddict[termname]
                for bd in bds:
                    #if bd.msb != None and bd.lsb != None and bd.ptr == None:
                    #    exit()
                    v = DFDataDepVisitor(self.terms, self.binddict)
                    items = v.visit(bd.tree)
                    for itemfull in items:
                        item = itemfull.termname
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

                if r[4] != None:
                    assert(target.rd_ptr == None or target.rd_ptr == r[4])
                    target.rd_ptr = r[4]
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

            merge_test = mergable(rlist)
            if merge_test[0] == True:
                #print("----------------------")
                #print("merge:", rlist[0])
                max_msb = merge_test[1]
                min_lsb = merge_test[2]
                r = (max_msb, min_lsb, rlist[0][0][2], rlist[0][0][3])
                rlist = [(r, rlist[0][1], rlist[0][2], rlist[0][3], rlist[0][4])]

            for (r, dst, dst_ptr, assigntype, alwaysinfo) in rlist:
                if r[0] != None:
                    dst_target = TargetEntry(dst, msb=df.DFEvalValue(r[0]),
                                        lsb=df.DFEvalValue(r[1]), ptr=dst_ptr)
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
                            if (saved_src_target == target and saved_conds == r[3] and
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


        return (prop_chain, reverse_map2, forward_map2)

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
            src_av = vast.And(sigma, self.get_valid_name(src))
            if base == None:
                base = src_av
            else:
                base = vast.Or(base, src_av)

        self.av_cache[target] = base
        return base

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
        return r

    def get_ai_q(self, target):
        return self.get_ai_name(target)

    # based on section 5.1 equation 3
    def get_assign(self, target, reverse_map):
        if target in self.assign_cache:
            return self.assign_cache[target]

        base = None
        for src, conds, assigntype, alwaysinfo in reverse_map[target]:
            sigma = self.get_merged_conds(conds)
            if base == None:
                base = sigma
            else:
                base = vast.Or(base, sigma)

        self.assign_cache[target] = base
        return base

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
        return r

    def get_valid_q(self, target):
        return self.get_valid_name(target)

    # based on section 5.1 equation 5
    def get_prop(self, target, prop_chain, forward_map, dff_map):
        if target in self.prop_cache:
            return self.prop_cache[target]

        assert(target in dff_map)
        rlist = []
        for dst, conds, assigntype, alwaysinfo in forward_map[target]:
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
                    rlist.append((ndst, vast.And(conds, self.get_merged_conds(ndst_conds))))
                rlist_changed = True

        base = None
        for dst, conds in rlist:
            if base == None:
                base = conds
            else:
                base = vast.Or(base, conds)

        self.prop_cache[target] = base
        return base

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
        return r

    def get_check(self, target, idx_override=None):
        tgt = copy.deepcopy(target)
        if idx_override != None:
            tgt.ptr = idx_override

        r = vast.IfStatement(vast.And(
                vast.Unot(vast.Or(self.get_good_q_name(tgt), self.get_prop_q_name(tgt))),
            self.get_assign_q_name(tgt)),
                vast.SingleStatement(vast.SystemCall("display", [
                    vast.StringConst("[%0t]" + target.toStr()),
                    vast.SystemCall("time", [])
                ])),
                None)

        return r

    def get_good_q(self, target):
        return self.get_good_name(target)

    def find2(self):
        prop_chain, reverse_map, forward_map = self.find_prop_chain()
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

        for n in prop_chain:
            if not n in reverse_map:
                continue

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
                senslist = alwaysinfo.original_senslist

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
                    for i in range(0, dim):
                        tmpn = copy.deepcopy(n)
                        tmpn.ptr = df.DFIntConst(str(i))
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
                for i in range(0, dim):
                    tmpn = copy.deepcopy(n)
                    tmpn.ptr = df.DFIntConst(str(i))
                    lblocking.append(vast.Assign(
                        vast.Lvalue(self.get_av_name(tmpn)),
                        vast.Rvalue(vast.And(
                            vast.Eq(vast.IntConst(str(i)), index_builder.visit(access_ptr)),
                            self.get_av(n, reverse_map)))))
                    lblocking.append(vast.Assign(
                        vast.Lvalue(self.get_ai_name(tmpn)),
                        vast.Rvalue(self.get_ai(n, reverse_map, idx_override=tmpn.ptr))))
                    lblocking.append(vast.Assign(
                        vast.Lvalue(self.get_assign_name(tmpn)),
                        vast.Rvalue(vast.And(
                            vast.Eq(vast.IntConst(str(i)), index_builder.visit(access_ptr)),
                            self.get_assign(n, reverse_map)))))
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
                    vast.Rvalue(self.get_assign(n, reverse_map))))
                lblocking.append(vast.Assign(
                    vast.Lvalue(self.get_valid_name(n)),
                    vast.Rvalue(self.get_valid(n, prop_chain, reverse_map, wire))))

        for n in dff_map:
            ldefs.append(self.get_prop_def(n))
            ldefs.append(self.get_prop_q_def(n))
            ldefs.append(self.get_good_def(n))
            ldefs.append(self.get_good_q_def(n))

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
            senslist = alwaysinfo.original_senslist

            if not senslist in lnonblocking:
                lnonblocking[senslist] = []

            if (n.ptr != None and n.ptr.__class__ != df.DFIntConst and n.ptr.__class__ != df.DFEvalValue):
                term = self.terms[n.termname]
                print("::::", n.toStr(), "::::", term.dims)
                dim = term.dims[0][0].eval() - term.dims[0][1].eval() + 1
                index_builder = DFBuildAstVisitor(self.terms, self.binddict)
                access_ptr = n.ptr if n.rd_ptr == None else n.rd_ptr
                for i in range(0, dim):
                    tmpn = copy.deepcopy(n)
                    tmpn.ptr = df.DFIntConst(str(i))
                    lnonblocking[senslist].append(vast.NonblockingSubstitution(
                        vast.Lvalue(self.get_prop_q_name(tmpn)),
                        vast.Rvalue(self.get_prop_q(tmpn))))
                    lblocking.append(vast.Assign(
                        vast.Lvalue(self.get_prop_name(tmpn)),
                        vast.Rvalue(
                            vast.And(
                                vast.Eq(vast.IntConst(str(i)), index_builder.visit(access_ptr)),
                                self.get_prop(n, prop_chain, forward_map, dff_map)))))

                    lnonblocking[senslist].append(vast.NonblockingSubstitution(
                        vast.Lvalue(self.get_good_q_name(tmpn)),
                        vast.Rvalue(self.get_good_q(tmpn))))
                    lblocking.append(vast.Assign(
                        vast.Lvalue(self.get_good_name(tmpn)),
                        vast.Rvalue(self.get_good(tmpn))))

                    lnonblocking[senslist].append(self.get_check(tmpn))

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

                lnonblocking[senslist].append(self.get_check(n))

        for n in m_in:
            for bbm in self.blackbox_modules:
                r = None
                r = self.blackbox_modules[bbm].instrument(self, n)
                if r != None:
                    linsts.append(r)

        for n in m_out:
            for bbm in self.blackbox_modules:
                r = None
                r = self.blackbox_modules[bbm].instrument(self, n)
                if r != None:
                    linsts.append(r)

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
            self.ast.items.append(vast.Always(
                    senslist,
                    vast.Block(lnonblocking[senslist])))



        

