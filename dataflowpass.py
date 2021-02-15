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

from gephistreamer import graph
from gephistreamer import streamer

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

    def visit_DFIntConst(self, node):
        value = node.eval()
        return vast.IntConst(str(value))

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

#class DFWidthVisitor:
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
#        for child in node.children():
#            self.visit(child)
#
#    def visit_DFTerminal(self, node):
#        termname = node.name
#        assert(len(termname.scopechain) == 2)
#        termmeta = self.terms[termname]
#        if 'Rename' in termmeta.termtype:
#            binds = self.binddict[termname]
#            assert(len(binds) == 1)
#            bd = binds[0]
#            assert(bd.lsb == None and bd.msb == None and bd.ptr == None)
#            self.visit(bd.tree)
#        else:
#            print(self.stack)




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
        else:
            width = termmeta.msb.eval() - termmeta.lsb.eval() + 1

        if termname != self.target.termname:
            return (None, None, width, None)

        if self.target.msb == None and self.target.lsb == None:
            condlist = self.condlist_copy_dedup(self.branch_stack)
            if condlist.__class__ == str:
                return (None, None, width, None)
            else:
                return (termmeta.msb.eval(), termmeta.lsb.eval(), width, condlist)

        assert(self.target.msb.eval() <= termmeta.msb.eval())
        assert(self.target.lsb.eval() >= termmeta.lsb.eval())

        condlist = self.condlist_copy_dedup(self.branch_stack)
        if condlist.__class__ == str:
            return (None, None, width, None)
        return (self.target.msb.eval(), self.target.lsb.eval(), width, condlist)

    def visit_DFPointer(self, node):
        var = node.var
        assert(var.__class__ == df.DFTerminal)
        ptr = node.ptr
        termname = node.var.name
        termmeta = self.terms[termname]
        width = termmeta.msb.eval() - termmeta.lsb.eval() + 1
        if termname != self.target.termname:
            return (None, None, width, None)
        if ptr != self.target.ptr:
            if ptr.__class__ != df.DFIntConst or self.target.ptr.__class__ != df.DFIntConst:
                pass
            else:
                return (None, None, width, None)
        
        r = self.visit(node.var)
        assert(r[2] == width)
        return r

    def visit_DFPartselect(self, node):
        r = self.visit(node.var)
        msb = node.msb.eval()
        lsb = node.lsb.eval()
        width = msb - lsb + 1
        child_msb = r[0]
        child_lsb = r[1]

        if child_msb == None and child_lsb == None:
            return (None, None, width, None)

        if msb >= child_msb and child_msb >= lsb and lsb >= child_lsb:
            return (child_msb - lsb, 0, width, r[3])

        if child_msb >= msb and msb >= child_lsb and child_lsb >= lsb:
            return (msb - lsb, child_lsb - lsb, width, r[3])

        if child_msb >= msb and lsb >= child_lsb:
            return (msb - lsb, 0, width, r[3])

        if msb >= child_msb and child_lsb >= lsb:
            return (child_msb - lsb, child_lsb - lsb, width, r[3])

        return (None, None, width, None)

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
                return (true_r[0], true_r[1], true_r[2], newlist)
        if true_r!= None and true_r[0] != None:
            return true_r
        elif false_r != None and false_r[0] != None:
            return false_r
        else:
            width = true_r[2] if true_r != None else false_r[2]
            return (None, None, width, None)

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
            tree = hit[0][3]
            for key in hit:
                assert(tree == hit[key][3])
                m = key + hit[key][0]
                l = key + hit[key][1]
                if max_m == None or m > max_m:
                    max_m = m
                if min_l == None or l < min_l:
                    min_l = l
            return (max_m, min_l, width, hit[0][3])
        elif r_valid_cnt == 1:
            return (curser + hit[curser][0], curser + hit[curser][1], width, hit[curser][3])
        else:
            return (None, None, width, None)

    def visit_DFOperator(self, node):
        if (node.operator == "And" or node.operator == "Or" or
                node.operator == "Plus" or node.operator == "Minus"):
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
                return (width - 1, 0, width, hit[0][3])
            else:
                return (None, None, width, None)
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
                return (0, 0, 1, hit[3])
            else:
                return (None, None, 1, None)
        elif node.operator == "Srl":
            assert(len(node.nextnodes) == 2)
            assert(node.nextnodes[1].__class__ == df.DFIntConst)
            sft = node.nextnodes[1].eval()
            r = self.visit(node.nextnodes[0])
            if r[0] == None:
                return (None, None, r[2], None)
            elif r[1] - sft >= 0:
                return (r[0] - sft, r[1] - sft, r[2], r[3])
            elif r[0] - sft >= 0:
                return (r[0] - sft, 0, r[2], r[3])
            else:
                return (None, None, r[2], None)
        elif node.operator == "Unot":
            assert(len(node.nextnodes) == 1)
            return self.visit(node.nextnodes[0])


        abort()

    def visit_DFIntConst(self, node):
        return (None, None, node.width(), None)


class TargetEntry:
    def __init__(self, termname, tree=None, msb=None, lsb=None, ptr=None):
        self.termname = termname
        self.msb = msb
        self.lsb = lsb
        self.ptr = ptr
        self.tree = tree

class RMapEntry:
    def __init__(self, dst, dst_msb, dst_lsb, dst_ptr, src, src_msb, src_lsb, src_ptr, tree):
        self.dst = dst
        self.src = src
        self.dst_msb = dst_msb
        self.dst_lsb = dst_lsb
        self.dst_ptr = dst_ptr
        self.src_msb = src_msb
        self.src_lsb = src_lsb
        self.src_ptr = src_ptr
        self.tree = tree

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
    def __init__(self, ast, terms, binddict, data_in, data_out):
        self.ast = ast
        self.terms = terms
        self.binddict = binddict
        self.data_in = util.toTermname(data_in)
        self.data_out = util.toTermname(data_out)
        self.vars = []
        self.queue = []
        self.parsed = {}

    def getTree(self, termname, msb=None, lsb=None, dim=None):
        binds = self.binddict[termname]
        for bd in binds:
            print(bd.dest, bd.tree)
        
    def test2(self, name):
        termname = util.toTermname(name)
        binds = self.binddict[termname]
        return binds

    def find2(self):
        self.queue.append(self.data_out)
        visited = {}
        reverse_map = {}
        stream = streamer.Streamer(streamer.GephiWS(hostname="localhost", port=8080, workspace="workspace1"))

        # the first pass, from destination to source
        while len(self.queue) > 0:
            left = self.queue[0]
            self.queue.pop(0)

            termname = left
            n = graph.Node(str(termname), size=10)
            n.color_hex(255, 0, 0)
            stream.add_node(n)
            visited[termname] = n
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
                        #print(item)
                        if not item in visited:
                            #print(item)
                            self.queue.append(item)
                            itemnode = graph.Node(str(item), size=10)
                            itemnode.color_hex(255, 0, 0)
                            visited[item] = itemnode
                        else:
                            itemnode = visited[item]
                        stream.add_node(itemnode)
                        e = graph.Edge(n, itemnode)
                        stream.add_edge(e)
                        rentry = RMapEntry(termname, bd.msb, bd.lsb, bd.ptr,
                                        item, itemfull.msb, itemfull.lsb, itemfull.ptr,
                                        bd.tree)
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
                                        rentry.src_msb == re.src_msb):
                                    exist = True
                                    break
                            if not exist:
                                reverse_map[item].append(rentry)


        # the second pass, from source to destination
        visited2 = set()
        self.queue.append(TargetEntry(self.data_in))
        while len(self.queue) > 0:
            target = self.queue[0]
            self.queue.pop(0)
            termname = target.termname

            if termname in visited2:
                continue
            visited2.add(termname)

            termmeta = self.terms[termname]
            #print("--------------------------")
            #print(termname, termmeta.msb, termmeta.lsb, termmeta.dims)
            #input('')

            if termname == self.data_out:
                continue

            print("=======================")
            print("target:", termname, target.msb, target.lsb, target.ptr, ", target cnt:", len(reverse_map[termname]))

            for itemfull in reverse_map[termname]:
                item = itemfull.dst
                if item in visited2:
                    continue

                print("----------------------")
                print("dst:", itemfull.dst, itemfull.dst_msb, itemfull.dst_lsb, itemfull.dst_ptr)
                print("src:", itemfull.src, itemfull.src_msb, itemfull.src_lsb, itemfull.src_ptr)

                v = DFPerciseDataDepVisitor(self.terms, self.binddict, target)
                r = v.visit(itemfull.tree)
                r = list(r)
                if r[0] != None and itemfull.dst_lsb != None:
                    r[0] += itemfull.dst_lsb.eval()
                    r[1] += itemfull.dst_lsb.eval()

                print(itemfull.dst, tuple(r), "added" if r[0] != None else "discarded")

                if r[0] != None:
                    self.queue.append(TargetEntry(item, msb=df.DFEvalValue(r[0]),
                                lsb=df.DFEvalValue(r[1]), ptr=itemfull.dst_ptr))
                    #self.queue.append(TargetEntry(item, msb=itemfull.dst_msb,
                    #            lsb=itemfull.dst_lsb, ptr=itemfull.dst_ptr))
                    itemnode = visited[item]
                    itemnode.color_hex(0, 255, 0)
                    stream.change_node(itemnode)



        for node in visited:
            if not node in visited2:
                stream.delete_node(visited[node])

        start = visited[self.data_in]
        start.color_hex(0, 0, 255)
        start.property["size"] = 25
        stream.change_node(start)
        end = visited[self.data_out]
        end.color_hex(0, 0, 255)
        end.property["size"] = 25
        stream.change_node(end)

        #for item in visited2:
        #    itemmeta = self.terms[item]
        #    print(item, itemmeta.msb, itemmeta.lsb, itemmeta.dims)


        for key in self.binddict:
            binds = self.binddict[key]
            for bd in binds:
                if bd.ptr == None:
                    continue
                if bd.parameterinfo == "nonblocking":
                    continue
                if bd.ptr.__class__ == df.DFEvalValue:
                    continue
                print(bd.dest, bd.parameterinfo, bd.alwaysinfo.senslist)








        

