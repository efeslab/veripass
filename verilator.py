import sys
import os
import math
import tempfile
import pathlib
sys.path.append(str(pathlib.Path(__file__).parent.absolute()/"Pyverilog"))
import pyverilog.vparser.ast as vast
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator
from passes.common import getWidthFromInt
from passes.WidthPass import WidthVisitor
import xml.etree.ElementTree as ET

from utils.ValueParsing import verilog_string_to_int

sys.setrecursionlimit(1000000)

class dtype:
    def __init__(self, width, array_len, type_name, signed=None):
        self.width = width
        self.array_len = array_len
        self.type_name = type_name
        self.signed = signed

class variable:
    def __init__(self, var_name, dtype_id, dtype):
        self.var_name = var_name
        self.dtype_id = dtype_id
        self.ref = []
        self.refcount = 1
        if dtype.array_len == 0:
            self.dff = []
            for i in range(0, dtype.width):
                self.dff.append(None)
        else:
            self.dff = []
            for i in range(0, dtype.array_len):
                self.dff.append([])
                for j in range(0, dtype.width):
                    self.dff[i].append(None)

class AstWidthVisitor(WidthVisitor):
    def __init__(self, typetable, used_vars):
        super().__init__()
        self.typetable = typetable
        self.used_vars = used_vars

    def visit_Identifier(self, node):
        name = node.name
        var_dtype_id = self.used_vars[name].dtype_id
        var_dtype = self.typetable[var_dtype_id]
        width = var_dtype.width
        self.widthtbl[node] = width

    def visit_Pointer(self, node):
        self.visit(node.var)
        self.widthtbl[node] = self.widthtbl[node.var]

class VerilatorXMLToAST:
    def __init__(self, top_module_name, xml_filename):
        self.top_module_name = top_module_name
        self.xml_filename = xml_filename
        self.typetable = {} # dtype_id -> dtype()
        self.used_vars = {} # var_name -> variable()
        self.scanned_vars = set()

        self.parser_stack = []
        self.split_var = False

        self.blackbox_inst = {} # name -> (defname, [params], [ports])
        self.astwidth_visitor = AstWidthVisitor(self.typetable, self.used_vars)

        self.jumpblock_stack = []
        self.while_variable_table = {}
    
    def name_format(self, name):
        s = name
        s = s.replace("(", "__028")
        s = s.replace(")", "__029")
        s = s.replace(":", "__03A")
        s = s.replace("__05F", "_")
        s = s.replace("TOP.", "", 1)
        s = s.replace(self.top_module_name+".", "", 1)
        s = s.replace(".", "__DOT__")
        s = s.replace("[", "__BRA__")
        s = s.replace("]", "__KET__")
        return s

    def get_parent_scope(self, name):
        s = self.name_format(name)
        r = s.rfind("__DOT__")
        if r == -1:
            return ""
        else:
            return s[:r]

    def get_direct_name(self, name):
        s = self.name_format(name)
        r = s.rfind("__DOT__")
        if r == -1:
            return s
        else:
            return s[r+len("__DOT__"):]

    
    def parse_files(self, fls):
        files = list(fls)
        fdict = {}
        for f in files:
            file_id = f.get("id")
            file_name = f.get("filename")
            file_lang = f.get("language")
            fdict[file_id] = {"filename": file_name, "lang": file_lang}
        return fdict
    
    def parse_cells(self, cls):
        return {}
    
    def parse_typetable(self, tptbl):
        type_table = list(tptbl)
        tptbl_size = len(type_table)
        tptbl_handled = 0
    
    
        while tptbl_handled < tptbl_size:
            for t in type_table:
                type_id = t.get("id")
                if type_id in self.typetable:
                    continue
                if t.tag == "unpackarraydtype" or t.tag == "packarraydtype":
                    # this type depends on a sub_dtype_id, which needs to be parsed
                    sub_dtype_id = t.get("sub_dtype_id")
                    if not sub_dtype_id in self.typetable:
                        #print(sub_dtype_id, "not found, continue")
                        continue
                    sub_dtype = self.typetable[sub_dtype_id]
                    assert(sub_dtype.array_len == 0) # the subtype must not be an array
                    r = list(t)
                    assert(len(r) == 1)
                    r = list(r[0])
                    assert(len(r) == 2)
                    assert(r[0].tag == "const")
                    assert(r[1].tag == "const")
                    left = r[0].get("name")
                    left = int(left.replace("32'sh", "0x").replace("32'h", "0x"), 16)
                    right = r[1].get("name")
                    right = int(right.replace("32'sh", "0x").replace("32'h", "0x"), 16)
                    #assert(right == 0)
                    assert(left >= 0)
                    width = sub_dtype.width
                    array_len = left - right + 1
                    if t.tag == "unpackarraydtype":
                        signed = True if t.get("signed")=="true" else False
                        self.typetable[type_id] = dtype(width, array_len, sub_dtype.type_name, signed)
                    else:
                        self.typetable[type_id] = dtype(width*array_len, 0, sub_dtype.type_name)
                    tptbl_handled += 1
                    #print(type_id, self.typetable[type_id])
                elif t.tag == "basicdtype":
                    type_type = t.get("name")
                    left = t.get("left")
                    if left == None:
                        left = "0"
                    right = t.get("right")
                    if right == None:
                        right = "0"
                    left = int(left)
                    right = int(right)
                    #assert(right == 0)
                    width = left - right + 1
                    array_len = 0 # 0 means it is not an array
                    signed = True if t.get("signed")=="true" else False
                    self.typetable[type_id] = dtype(width, array_len, type_type, signed)
                    tptbl_handled += 1
                    #print(type_id, self.typetable[type_id])
                elif t.tag == "enumdtype":
                    type_type = "logic"
                    width = int(math.log2(len(list(t))-1)+1)
                    array_len = 0
                    self.typetable[type_id] = dtype(width, array_len, type_type)
                    tptbl_handled += 1
                    #print(type_id, self.typetable[type_id])
                elif t.tag == "structdtype":
                    type_type = "logic"
                    width = 0
                    skip = False
                    for mem in list(t):
                        sub_dtype_id = mem.get("sub_dtype_id")
                        if not sub_dtype_id in self.typetable:
                            skip = True
                            #print(sub_dtype_id, "not found, continue")
                            break
                        assert(self.typetable[sub_dtype_id].array_len == 0) # subtype must not be an array
                        width += self.typetable[sub_dtype_id].width
                    if skip:
                        continue
                    array_len = 0
                    self.typetable[type_id] = dtype(width, array_len, type_type)
                    tptbl_handled += 1
                    #print(type_id, self.typetable[type_id])
                elif t.tag == "refdtype":
                    sub_dtype_id = t.get("sub_dtype_id")
                    if not sub_dtype_id in self.typetable:
                        #print(sub_dtype_id, "not found, continue")
                        continue
                    self.typetable[type_id] = self.typetable[sub_dtype_id]
                    tptbl_handled += 1
                    #print(type_id, self.typetable[type_id])
                else:
                    #print(t.tag)
                    assert(0 and "meh")
    
    def parse_elem(self, elem):
        method = "parse_elem_" + elem.tag
        func = getattr(self, method)
        assert(func != None)
        self.parser_stack.append(elem.tag)
        r = func(elem)
        self.parser_stack.pop()
        return r
    
    def parse_elem_const(self, elem):
        assert(elem.tag == "const")
        return vast.IntConst(elem.get("name"))

    def parse_elem_comment(self, elem):
        assert(elem.tag == "comment")
        return vast.CommentStmt(elem.get('name'))
    
    def parse_elem_varref(self, elem):
        assert(elem.tag == "varref")
        var_name = self.name_format(elem.get("hier"))
        var_dtype = self.typetable[self.used_vars[var_name].dtype_id]
        r = vast.Identifier(self.name_format(elem.get("hier")))
        self.used_vars[var_name].ref.append(r)

        if var_name in self.while_variable_table:
            return vast.IntConst("32'h"+hex(self.while_variable_table[var_name])[2:])

        # DFF detection
        if self.parser_stack[0] != "initial":
            # If the left-side of an assigndly is a varref, then the whole var
            # should be an DFF.
            if self.parser_stack[-2] == "assigndly:left":
                assert(var_dtype.array_len == 0) # array should not be signed directly
                for i in range(0, var_dtype.width):
                    #print(var_name, i)
                    assert(self.used_vars[var_name].dff[i] == True or
                            self.used_vars[var_name].dff[i] == None)
                    self.used_vars[var_name].dff[i] = True
            elif self.parser_stack[-2] == "assign:left":
                assert(var_dtype.array_len == 0)
                for i in range(0, var_dtype.width):
                    assert(self.used_vars[var_name].dff[i] == False or
                            self.used_vars[var_name].dff[i] == None)
                    self.used_vars[var_name].dff[i] = False

        return r
    
    def parse_elem_sel(self, elem):
        assert(elem.tag == "sel")
        l = list(elem)
        #assert(l[0].tag == "varref" or l[0].tag == "arraysel")
        varref = self.parse_elem(l[0])
        start = self.parse_elem(l[1])
        assert(l[2].tag == "const")
        width = self.parse_elem(l[2])

        if varref.__class__ == vast.IntConst:
            if start.__class__ == vast.IntConst and width.__class__ == vast.IntConst:
                var_value = verilog_string_to_int(varref.value)
                start_value = verilog_string_to_int(start.value)
                width_value = verilog_string_to_int(width.value)

                tmp = ''
                for i in range(0, 64):
                    tmp += '0'

                binary = tmp + bin(var_value)[2:]
                length = len(binary)
                
                selected = binary[length - start_value - width_value : length - start_value + 1]

                return vast.IntConst(str(width_value) + "'h" + hex(int(selected, 2))[2:])
    
        #print(start.__class__)
        #print(start.__class__ == vast.IntConst)
    
        if start.__class__ == vast.IntConst:
            start_value_pos = start.value.find("h")
            assert(start_value_pos != -1)
            start_value = verilog_string_to_int(start.value)
            assert(start_value == int("0x"+start.value[start_value_pos+1:], 16))
            width_value_pos = width.value.find("h")
            assert(width_value_pos != -1)
            width_value = verilog_string_to_int(width.value)
            assert(width_value == int("0x"+width.value[width_value_pos+1:], 16))
            msb = start_value + width_value - 1
            lsb = start_value
            r = vast.Partselect(varref, vast.IntConst(str(msb)), vast.IntConst(str(lsb)))
        else:
            width_value_pos = width.value.find("h")
            assert(width_value_pos != -1)
            width_value = verilog_string_to_int(width.value)
            assert(width_value == int("0x"+width.value[width_value_pos+1:], 16))
            if width_value == 1:
                r = vast.Partselect(varref, start, start)
            else:
                # wire[base+const:base]
                r = vast.Partselect(varref,
                        vast.Plus(start, vast.IntConst(str(width_value-1))),
                        start)
            # TODO: do we want to handle other types of variable width? like [ a -: b ] ?

        ## DFF detection
        if self.parser_stack[0] != "initial":
            ## arr[3:0] <= ...
            if varref.__class__ == vast.Identifier:
                var_dtype_id = self.used_vars[varref.name].dtype_id
                var_dtype = self.typetable[var_dtype_id]
                assert(var_dtype.array_len == 0)

                if self.parser_stack[-2] == "assigndly:left" or self.parser_stack[-2] == "assign:left":
                    isdff = True if self.parser_stack[-2] == "assigndly:left" else False

                    # if msb and lsb are both IntConst, var[msb:lsb] is dff
                    if r.msb.__class__ == vast.IntConst and r.lsb.__class__ == vast.IntConst:
                        msb = int(r.msb.value)
                        lsb = int(r.lsb.value)
                        assert(msb >= lsb and msb < var_dtype.width and lsb >= 0)
                        for i in range(lsb, msb+1):
                            assert(self.used_vars[varref.name].dff[i] == isdff or
                                    self.used_vars[varref.name].dff[i] == None)
                            self.used_vars[varref.name].dff[i] = isdff
                    # if lsb is not IntConst, we assume this implies the whole var is dff
                    # TODO: this may not be complete, if weird things happen, an assertion
                    else:
                        assert(r.lsb.__class__ == vast.Pointer or r.lsb.__class__ == vast.Partselect
                                or r.lsb.__class__ == vast.Identifier)
                        for i in range(0, var_dtype.width):
                            assert(self.used_vars[varref.name].dff[i] == isdff or
                                    self.used_vars[varref.name].dff[i] == None)
                            self.used_vars[varref.name].dff[i] = isdff
            elif varref.__class__ == vast.Pointer:
                arr = varref.var
                idx = varref.ptr
                assert(arr.__class__ == vast.Identifier)
                arr_dtype_id = self.used_vars[arr.name].dtype_id
                arr_dtype = self.typetable[arr_dtype_id]
                assert(arr_dtype.array_len != 0)

                if self.parser_stack[-2] == "assigndly:left" or self.parser_stack[-2] == "assign:left":
                    isdff = True if self.parser_stack[-2] == "assigndly:left" else False

                    # if msb and lsb are both IntConst, var[msb:lsb] is dff
                    if r.msb.__class__ == vast.IntConst and r.lsb.__class__ == vast.IntConst:
                        msb = int(r.msb.value)
                        lsb = int(r.lsb.value)
                        assert(msb >= lsb and msb < arr_dtype.width and lsb >= 0)
                        # if the ArraySelect has a constant index, mark arr[k][msb:lsb] as dff
                        if idx.__class__ == vast.IntConst:
                            value_pos = idx.value.find("h")
                            assert(value_pos != -1)
                            value = verilog_string_to_int(idx.value)
                            assert(value == int("0x"+idx.value[value_pos+1:], 16))
                            for i in range(lsb, msb+1):
                                assert(self.used_vars[arr.name].dff[value][i] == isdff or
                                        self.used_vars[arr.name].dff[value][i] == None)
                                self.used_vars[arr.name].dff[value][i] = isdff
                        # if the ArraySelect has a variable index, mark arr[any][msb:lsb] as dff
                        else:
                            for i in range(0, arr_dtype.array_len):
                                for j in range(lsb, msb+1):
                                    assert(self.used_vars[arr.name].dff[i][j] == isdff or
                                            self.used_vars[arr.name].dff[i][j] == None)
                                    self.used_vars[arr.name].dff[i][j] = isdff
                    # if lsb is not IntConst, we assume this implies the whole var is dff
                    # TODO: this may not be complete, if weird things happen, an assertion
                    else:
                        assert(r.lsb.__class__ == vast.Pointer or r.lsb.__class__ == vast.Partselect
                                or r.lsb.__class__ == vast.Identifier)
                        if idx.__class__ == vast.IntConst:
                            value_pos = idx.value.find("h")
                            assert(value_pos != -1)
                            value = verilog_string_to_int(idx.value)
                            assert(value == int("0x"+idx.value[value_pos+1:], 16))
                            for i in range(0, arr_dtype.width):
                                assert(self.used_vars[arr.name].dff[value][i] == isdff or
                                        self.used_vars[arr.name].dff[value][i] == None)
                                self.used_vars[arr.name].dff[value][i] = isdff
                        else:
                            for i in range(0, arr_dtype.array_len):
                                for j in range(0, arr_dtype.width):
                                    assert(self.used_vars[arr.name].dff[i][j] == isdff or
                                            self.used_vars[arr.name].dff[i][j] == None)
                                    self.used_vars[arr.name].dff[i][j] = isdff

        return r
    
    def parse_elem_assigndly(self, elem):
        assert(elem.tag == "assigndly")

        l = list(elem)
        assert(len(l) == 2)
        self.parser_stack[-1] = "assigndly:right"
        right = self.parse_elem(l[0])
        self.parser_stack[-1] = "assigndly:left"
        left = self.parse_elem(l[1])

        return vast.NonblockingSubstitution(vast.Lvalue(left), vast.Rvalue(right))
    
    def parse_elem_assign(self, elem):
        assert(elem.tag == "assign")
        l = list(elem)
        assert(len(l) == 2)
        self.parser_stack[-1] = "assign:right"
        right = self.parse_elem(l[0])
        self.parser_stack[-1] = "assign:left"
        left = self.parse_elem(l[1])

        return vast.BlockingSubstitution(vast.Lvalue(left), vast.Rvalue(right))
    
    def parse_elem_cond(self, elem):
        assert(elem.tag == "cond")
        l = list(elem)
        assert(len(l) == 3)
        cond = self.parse_elem(l[0])
        cond_then = self.parse_elem(l[1])
        cond_else = self.parse_elem(l[2])
        return vast.Cond(cond, cond_then, cond_else)
    
    def parse_elem_condbound(self, elem):
        assert(elem.tag == "condbound")
        l = list(elem)
        assert(len(l) == 3)
        cond = self.parse_elem(l[0])
        cond_then = self.parse_elem(l[1])
        cond_else = self.parse_elem(l[2])
        return vast.Cond(cond, cond_then, cond_else)
    
    def parse_elem_add(self, elem):
        assert(elem.tag == "add")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])

        if a.__class__ == vast.IntConst and b.__class__ == vast.IntConst:
            a_value = verilog_string_to_int(a.value)
            b_value = verilog_string_to_int(b.value)
            a_width = a.value[0:a.value.find("'h")+2]
            b_width = b.value[0:b.value.find("'h")+2]
            if a_width == b_width:
                return vast.IntConst(a_width+hex(a_value+b_value)[2:])

        return vast.Plus(a, b)
    
    def parse_elem_sub(self, elem):
        assert(elem.tag == "sub")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])

        if a.__class__ == vast.IntConst and b.__class__ == vast.IntConst:
            a_value = verilog_string_to_int(a.value)
            b_value = verilog_string_to_int(b.value)
            a_width = a.value[0:a.value.find("'h")+2]
            b_width = b.value[0:b.value.find("'h")+2]
            if a_width == b_width:
                return vast.IntConst(a_width+hex(a_value-b_value)[2:])

        return vast.Minus(a, b)
    
    def parse_elem_muls(self, elem):
        assert(elem.tag == "muls")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Times(a, b)
    
    def parse_elem_mul(self, elem):
        assert(elem.tag == "mul")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Times(a, b)

    def parse_elem_moddiv(self, elem):
        assert(elem.tag == "moddiv")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Mod(a, b)
    
    def parse_elem_divs(self, elem):
        assert(elem.tag == "divs")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Divide(a, b)
    
    def parse_elem_div(self, elem):
        assert(elem.tag == "div")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Divide(a, b)
    
    def parse_elem_and(self, elem):
        assert(elem.tag == "and")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.And(a, b)
    
    def parse_elem_xor(self, elem):
        assert(elem.tag == "xor")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Xor(a, b)
    
    def parse_elem_or(self, elem):
        assert(elem.tag == "or")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Or(a, b)
    
    def parse_elem_eq(self, elem):
        assert(elem.tag == "eq")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Eq(a, b)
    
    def parse_elem_shiftr(self, elem):
        assert(elem.tag == "shiftr")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Srl(a, b)
    
    def parse_elem_shiftl(self, elem):
        assert(elem.tag == "shiftl")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Sll(a, b)
    
    def parse_elem_redand(self, elem):
        assert(elem.tag == "redand")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        return vast.Uand(a)

    def parse_elem_redor(self, elem):
        assert(elem.tag == "redor")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        return vast.Uor(a)
    
    def parse_elem_eqcase(self, elem):
        assert(elem.tag == "eqcase")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.Eql(a, b)
    
    def parse_elem_lte(self, elem):
        assert(elem.tag == "lte")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.LessEq(a, b)
    
    def parse_elem_lt(self, elem):
        assert(elem.tag == "lt")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.LessThan(a, b)
    
    def parse_elem_gte(self, elem):
        assert(elem.tag == "gte")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.GreaterEq(a, b)
    
    def parse_elem_gt(self, elem):
        assert(elem.tag == "gt")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.GreaterThan(a, b)
    
    def parse_elem_neq(self, elem):
        assert(elem.tag == "neq")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
        return vast.NotEq(a, b)

    def parse_elem_lognot(self, elem):
        assert(elem.tag == "lognot")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        return vast.Ulnot(a)
    
    def parse_elem_not(self, elem):
        assert(elem.tag == "not")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        return vast.Unot(a)
    
    def parse_elem_negate(self, elem):
        assert(elem.tag == "negate")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        return vast.Uminus(a)

    def parse_elem_extend(self, elem):
        assert(elem.tag == "extend")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        width = vast.IntConst(elem.get("width"))
        tree_width = self.astwidth_visitor.getWidth(a)
        target_width = verilog_string_to_int(width.value)
        append_int = vast.IntConst("{}'h0".format(target_width - tree_width))
        if a.__class__ == vast.Concat:
            items = [append_int] + a.list
        else:
            items = [append_int, a]
        return vast.Concat(items)

    def parse_elem_extends(self, elem):
        assert(elem.tag == "extends")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        width = vast.IntConst(elem.get("width"))
        tree_width = self.astwidth_visitor.getWidth(a)
        target_width = verilog_string_to_int(width.value)
        append_int_pos = vast.IntConst("{}'h0".format(target_width - tree_width))
        append_int_neg = vast.IntConst("{}'h1".format(target_width - tree_width))
        append_int = vast.Cond(
                vast.Partselect(a, vast.IntConst(str(tree_width-1)), vast.IntConst(str(tree_width-1))),
                append_int_neg,
                append_int_pos)
        if a.__class__ == vast.Concat:
            items = [append_int] + a.list
        else:
            items = [append_int, a]
        return vast.Concat(items)

    def parse_elem_replicate(self, elem):
        assert(elem.tag == "replicate")
        l = list(elem)
        assert(len(l) == 2)
        value = self.parse_elem(l[0])
        times = self.parse_elem(l[1])
        assert(times.__class__ == vast.IntConst)
        tv = times.value.replace("32'sh", "0x").replace("32'h", "0x")
        tv = str(int(tv, 16))
        times.value = tv
        return vast.Repeat(value, times)
    
    def parse_elem_concat(self, elem):
        assert(elem.tag == "concat")
        l = list(elem)
        assert(len(l) == 2)
        items = []
        for child in l:
            items.append(self.parse_elem(child))
        comb_items = []
        for it in items:
            if it.__class__ == vast.Concat:
                comb_items += it.list
            else:
                comb_items.append(it)
        return vast.Concat(comb_items)
        #return vast.Concat(items)
    
    def parse_elem_cmath(self, elem):
        assert(elem.tag == "cmath")
        l = list(elem)
        assert(len(l) == 1)
        assert(l[0].tag == "text")
        assert(l[0].get("name") == "Verilated::assertOn()")
        return vast.Identifier("ASSERT_ON")
    
    def parse_elem_time(self, elem):
        assert(elem.tag == "time")
        return vast.SystemCall("time", [])
    
    def parse_elem_stop(self, elem):
        assert(elem.tag == "stop")
        return vast.SingleStatement(vast.SystemCall("stop", []))

    def parse_elem_readmem(self, elem):
        assert(elem.tag == "readmem")
        l = list(elem)
        assert(l[0].tag == "const")
        assert(l[0].get("from_string") == "true")
        assert(l[1].tag == "varref")
        filename = vast.StringConst(l[0].get("str"))
        varref = self.parse_elem(l[1])
        return vast.SingleStatement(vast.SystemCall("readmemh", [filename, varref]))

    def parse_elem_scopename(self, elem):
        assert(elem.tag == "scopename")
        return vast.StringConst(elem.get("name"))

    def parse_elem_display(self, elem):
        assert(elem.tag == "display")
        l = list(elem)
        assert(len(l) == 1)
        assert(l[0].tag == "sformatf")
        fmt = l[0].get("name").replace("\n", "\\n")
        if fmt[-2:] == "\\n":
            fmt = fmt[:-2]
        args = []
        args.append(vast.StringConst(fmt))
        for arg in list(l[0]):
            #assert(arg.tag == "time" or arg.tag == "scopename")
            if arg.tag == "scopename":
                args[0] = vast.StringConst(fmt.replace("%m", arg.get("name")))
                continue
            args.append(self.parse_elem(arg))
        return vast.SingleStatement(vast.SystemCall("display", args, anno=elem.get("tag")))
    
    def parse_elem_finish(self, elem):
        assert(elem.tag == "finish")
        return vast.SingleStatement(vast.SystemCall("finish", []))
    
    def parse_elem_arraysel(self, elem):
        assert(elem.tag == "arraysel")
        l = list(elem)
        assert(len(l) == 2)

        arr = self.parse_elem(l[0])
        arr_dtype_id = self.used_vars[arr.name].dtype_id
        arr_dtype = self.typetable[arr_dtype_id]
        assert(arr_dtype.array_len != 0)

        idx = self.parse_elem(l[1])

        ## DFF detection
        if self.parser_stack[0] != "initial":
            ## arr[i] <= ...
            if self.parser_stack[-2] == "assigndly:left" or self.parser_stack[-2] == "assign:left":
                isdff = True if self.parser_stack[-2] == "assigndly:left" else False

                # if the idx is IntConst, arr[idx] is dff
                if idx.__class__ == vast.IntConst:
                    value_pos = idx.value.find("h")
                    assert(value_pos != -1)
                    value = verilog_string_to_int(idx.value)
                    assert(value == int("0x"+idx.value[value_pos+1:], 16))
                    for i in range(0, arr_dtype.width):
                        #print(arr_dtype_id, arr_dtype.array_len, arr_dtype.width, arr.name, value,
                        #        self.used_vars[arr.name].dff[value][i], self.parser_stack[-2], isdff)
                        assert(self.used_vars[arr.name].dff[value][i] == isdff or
                                self.used_vars[arr.name].dff[value][i] == None)
                        self.used_vars[arr.name].dff[value][i] = isdff
                # if the idx is Identifier, the arr with any index is dff
                elif idx.__class__ == vast.Identifier:
                    for i in range(0, arr_dtype.array_len):
                        for j in range(0, arr_dtype.width):
                            assert(self.used_vars[arr.name].dff[i][j] == isdff or
                                    self.used_vars[arr.name].dff[i][j] == None)
                            self.used_vars[arr.name].dff[i][j] = isdff
                # if the idx is partselect, the arr with any index is dff
                elif idx.__class__ == vast.Partselect:
                    assert(idx.var.__class__ == vast.Identifier)
                    for i in range(0, arr_dtype.array_len):
                        for j in range(0, arr_dtype.width):
                            assert(self.used_vars[arr.name].dff[i][j] == isdff or
                                    self.used_vars[arr.name].dff[i][j] == None)
                            self.used_vars[arr.name].dff[i][j] = isdff
                # otherwise we have no idea what's going on, leave it empty
                else:
                    pass

        return vast.Pointer(arr, idx)
    
    def parse_elem_if(self, elem):
        assert(elem.tag == "if")
        l = list(elem)
        ifs_cnt = int(elem.get("ifs_cnt"))
        elses_cnt = int(elem.get("elses_cnt"))
        #print("======", ifs_cnt, elses_cnt)
        assert(len(l) == ifs_cnt + elses_cnt + 1)
        if_cond = self.parse_elem(l[0])
        if_then = []
        for i in range(1, 1+ifs_cnt):
            #print("----", i)
            if_then.append(self.parse_elem(l[i]))
            if if_then[-1] == None:
                if_then.pop()
        if_else = []
        for i in range(1+ifs_cnt, 1+ifs_cnt+elses_cnt):
            #print("----", i)
            if_else.append(self.parse_elem(l[i]))
            if if_else[-1] == None:
                if_else.pop()
        if_branch = vast.Block(if_then)
        if len(if_else) == 1 and if_else[0].__class__ == vast.IfStatement:
            else_branch = if_else[0]
        elif len(if_else) > 0:
            else_branch = vast.Block(if_else)
        else:
            else_branch = None
        return vast.IfStatement(if_cond, if_branch, else_branch)

    # The handling of jumpblock is a huge hack. This following code can only handle the case where:
    #   1. The jumpblock only contains an while block
    #   2. The while block only contains an if-statement with only then-branch
    #   3. The while block starts from 0, adds by 1 at each iteration, and use gts to compare
    #   4. There's a jump at the end of the if-statement and that's the only jump
    def parse_elem_jumpblock(self, elem):
        assert(elem.tag == "jumpblock")
        l = list(elem)
        assert(len(l) == 2)
        assert(l[0].tag == "while")
        assert(l[1].tag == "jumplabel")
        self.jumpblock_stack.append(elem)
        w = list(l[0])
        assert(len(w) == 3)
        assert(w[0].tag == "gts")
        assert(w[1].tag == "if")
        assert(w[2].tag == "assign")

        gts = list(w[0])
        assign = list(w[2])

        upper_bound = verilog_string_to_int(gts[0].get("name"))
        iter_var_name = self.name_format(gts[1].get("hier"))
        self.while_variable_table[iter_var_name] = 0

        r = None
        it = None
        for i in range(0, upper_bound):
            self.while_variable_table[iter_var_name] = i
            if r == None:
                r = self.parse_elem(w[1])
                it = r
            else:
                it.false_statement = self.parse_elem(w[1])
                it = it.false_statement
        return r

    def parse_elem_jumpgo(self, elem):
        assert(elem.tag == "jumpgo")
        assert(len(self.jumpblock_stack) > 0)
        return None
    
    def parse_assign(self, assign):
        l = list(assign)
        self.parser_stack[-1] = "assign:right"
        right = self.parse_elem(l[0])
        self.parser_stack[-1] = "assign:left"
        left = self.parse_elem(l[1])

        if left.__class__ == vast.Identifier and self.get_parent_scope(left.name) in self.blackbox_inst:
            port = vast.PortArg(self.get_direct_name(left.name), right)
            self.blackbox_inst[self.get_parent_scope(left.name)][2].append(port)
            return None
        elif right.__class__ == vast.Identifier and self.get_parent_scope(right.name) in self.blackbox_inst:
            port = vast.PortArg(self.get_direct_name(right.name), left)
            self.blackbox_inst[self.get_parent_scope(right.name)][2].append(port)
            return None
        else:
            return vast.Assign(vast.Lvalue(left), vast.Rvalue(right))
    
    def parse_initial(self, initial):
        items = []
        self.parser_stack.append("initial")
        for elem in list(initial):
            if elem.tag == "assign":
                self.parser_stack.append("assign")
                l = list(elem)
                self.parser_stack[-1] = "assign:right"
                right = self.parse_elem(l[0])
                self.parser_stack[-1] = "assign:left"
                left = self.parse_elem(l[1])
                items.append(vast.Substitution(vast.Lvalue(left), vast.Rvalue(right)))
                self.parser_stack.pop()
            else:
                items.append(self.parse_elem(elem))
                if items[-1] == None:
                    items.pop()
        self.parser_stack.pop()
        return items
    
    def parse_always(self, always, senslist):
        items = []
        self.parser_stack.append("always")
        for elem in list(always):
            if elem.tag != "comment":
                items.append(self.parse_elem(elem))
                if items[-1] == None:
                    items.pop()
        self.parser_stack.pop()
        if len(items) == 0:
            return None
        else:
            return vast.Always(senslist, vast.Block(items))
    
    def parse_active(self, active):
        items = []
        sentree = active.find("sentree")
        active_name = active.get("name")
        if active_name == "combo":
            l = list(active)
            assert(l[0].tag == "sentree")
            assert(l[0].find("senitem").get("edgeType") == "COMBO")
            for assign in l[1:]:
                #assert (assign.tag != "assignalias")
                #if assign.tag == "assignalias":
                #    continue
                #assert(assign.tag == "assign" or assign.tag == "contassign")
                senslist = vast.SensList([vast.Sens(vast.Identifier(""), type="all")])
                if assign.tag == "assign" or assign.tag == "contassign":
                    self.parser_stack.append("assign")
                    asgn = self.parse_assign(assign)
                    if asgn != None:
                        items.append(asgn)
                    self.parser_stack.pop()
                elif assign.tag == "always":
                    alwys = self.parse_always(assign, senslist)
                    if alwys != None:
                        items.append(alwys)
        elif active_name == "initial":
            l = list(active)
            initial_items = []
            assert(l[0].tag == "sentree")
            assert(l[0].find("senitem").get("edgeType") == "INITIAL")
            for initial in l[1:]:
                assert(initial.tag == "initial")
                initial_items += self.parse_initial(initial)
            items.append(vast.Initial(vast.Block(initial_items)))
        elif active_name == "sequent":
            l = list(active)
            sens = []
            for senitem in l[0].findall("senitem"):
                sl = list(senitem)
                assert(len(sl) == 1)
                assert(sl[0].tag == "varref")
                sens_type = senitem.get("edgeType")
                if sens_type == "BOTH":
                    sens.append(vast.Sens(
                        vast.Identifier(self.name_format(sl[0].get("name"))), type="posedge"))
                    sens.append(vast.Sens(
                        vast.Identifier(self.name_format(sl[0].get("name"))), type="negedge"))
                else:
                    if sens_type == "POS":
                        sens_type = "posedge"
                    elif sens_type == "NEG":
                        sens_type = "negedge"
                    sens.append(vast.Sens(
                            vast.Identifier(self.name_format(sl[0].get("name"))), type=sens_type))
            senslist = vast.SensList(sens)
            for always in l[1:]:
                new_items = self.parse_always(always, senslist)
                if new_items != None:
                    items.append(new_items)
        else:
            assert(0 and "meh")
    
        return items
    
    
    def parse_module(self, module, iface_vars):
        params = []
        ports = []
        items = []
    
    
        params.append(vast.Parameter("ASSERT_ON", vast.Constant("1'b1")))

        for var in module.findall('var'):
            var_name = self.name_format(var.get("name"))
            if var_name in self.scanned_vars:
                print(var_name, "rescanned, ignoring...")
                continue
            self.scanned_vars.add(var_name)

            var_type_id = var.get("dtype_id")
            var_type = self.typetable[var_type_id]
            var_type_name = var_type.type_name
            var_type_width = var_type.width
            #assert(var_type_width > 0)
            if var_type_width <= 0:
                print("warning: {} width is 0".format(var.get("name")))
            var_type_array_len = var_type.array_len
            var_dir = var.get("dir")
    
            width = None
            dim = None
            width = vast.Width(vast.IntConst(str(var_type_width-1)), vast.IntConst(str(0)))
            if var_type_array_len != 0:
                lth = vast.Width(vast.IntConst(str(var_type_array_len-1)), vast.IntConst(str(0)))
                dim = vast.Dimensions([lth])

            signed = var_type.signed
            if signed == None:
                signed = False

            anno = var.get('tag')
            if self.split_var and (width != None or dim != None):
                if anno:
                    raise NotImplementedError("annotation cannot use for both metacomments and split_var")
                else:
                    anno = "verilator split_var"

            if var_dir == "input":
                assert(dim == None)
                p = vast.Ioport(vast.Input(var_name, width=width), vast.Logic(var_name, width=width, signed=signed))
                ports.append(p)
            elif var_dir == "output":
                assert(dim == None)
                p = vast.Ioport(vast.Output(var_name, width=width), vast.Logic(var_name, width=width, signed=signed))
                ports.append(p)
            elif var_name in self.used_vars:
                assert(var_dir == None)
                if var.get("param") == "true":
                    l = list(var)
                    assert(len(l) == 1 and l[0].tag == "const")
                    p = vast.Parameter(var_name, self.parse_elem(l[0]))
                    items.append(p)
                elif var_type_name == "logic":
                    p = vast.Logic(var_name, width=width, dimensions=dim, annotation=anno, signed=signed)
                    items.append(p)
                elif var_type_name == "int":
                    p = vast.Logic(var_name, width=width, dimensions=dim, signed=signed)
                    items.append(p)
                elif var_type_name == "integer":
                    p = vast.Integer(var_name, width=width, dimensions=dim, signed=signed)
                    items.append(p)
                elif var_type_name == "reg":
                    p = vast.Reg(var_name, width=width, dimensions=dim, annotation=anno, signed=signed)
                    items.append(p)
                elif var_type_name == "wire":
                    p = vast.Wire(var_name, width=width, dimensions=dim, annotation=anno, signed=signed)
                    items.append(p)
                elif var_type_name == "time":
                    p = vast.Time(var_name)
                    items.append(p)
                elif var_type_name == "bit":
                    p = vast.Logic(var_name, width=width, dimensions=dim)
                    items.append(p)
                else:
                    assert(0)
        params = vast.Paramlist(params)
        ports = vast.Portlist(ports)
    
        items += iface_vars
    
        for active in module.find("topscope").find("scope").findall("active"):
            items += self.parse_active(active)
    
        for inst_name in self.blackbox_inst:
            inst_info = self.blackbox_inst[inst_name]
            inst = vast.Instance(inst_info[0], inst_name, inst_info[2], inst_info[1])
            inst_list = vast.InstanceList(inst_info[0], inst_info[1], [inst])
            items.append(inst_list)
    
        ast = vast.ModuleDef(self.top_module_name, params, ports, items)
    
        #codegen = ASTCodeGenerator()
        #rslt = codegen.visit(ast)
        #print(rslt)
    
        return ast
    
    def parse_iface(self, iface):
        items = []
        for scope in iface.findall("scope"):
            for var in scope.findall("varscope"):
                if not self.name_format(var.get("name")) in self.used_vars:
                    continue
    
                var_name = self.name_format(var.get("name"))
                var_type_id = var.get("dtype_id")
                var_type = self.typetable[var_type_id]
                var_type_name = var_type.type_name
                var_type_width = var_type.width
                assert(var_type_width > 0)
                var_type_array_len = var_type.array_len
                var_dir = var.get("dir")
    
                width = None
                dim = None
                if var_type_width > 1:
                    width = getWidthFromInt(var_type_width)
                if var_type_array_len != 0:
                    dim = vast.Dimensions([getWidthFromInt(var_type_array_len)])

                anno = None
                if self.split_var and (width != None or dim != None):
                    anno = "verilator split_var"
    
                assert(var_dir == None)
                if var.get("param") == "true":
                    l = list(var)
                    assert(len(l) == 1 and l[0].tag == "const")
                    p = vast.Parameter(var_name, self.parse_elem(l[0]))
                    items.append(p)
                elif var_type_name == "logic":
                    p = vast.Logic(var_name, width=width, dimensions=dim, annotation=anno)
                    items.append(p)
                elif var_type_name == "int":
                    p = vast.Logic(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "integer":
                    p = vast.Integer(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "reg":
                    p = vast.Reg(var_name, width=width, dimensions=dim, annotation=anno)
                    items.append(p)
                elif var_type_name == "wire":
                    p = vast.Wire(var_name, width=width, dimensions=dim, annotation=anno)
                    items.append(p)
    
        return items
    
    def used_varref(self, nlst):
        for varref in nlst.iter("varref"):
            var_name = self.name_format(varref.get("hier"))
            dtype_id = varref.get("dtype_id")
            dtype = self.typetable[dtype_id]
            if not var_name in self.used_vars:
                self.used_vars[var_name] = variable(var_name, dtype_id, dtype)
            else:
                self.used_vars[var_name].refcount += 1

    def used_blackbox_module(self, nlst):
        top_mod = None
        blkbox_rename = {}
        for mod in nlst.findall("module"):
            if mod.get("origName") != "TOP":
                blkbox_rename[mod.get("name")] = mod.get("origName")
            else:
                top_mod = mod
        for instance in top_mod.iter("instance"):
            inst_type = instance.get("instance_type")
            defname = instance.get("defName")
            if inst_type == "module":
                assert(defname in blkbox_rename)
                blackbox_inst_entry = (blkbox_rename[defname], [], [])
                self.blackbox_inst[self.name_format(instance.get("name"))] = blackbox_inst_entry
                for port in list(instance):
                    assert(port.tag == "port")
                    assert(len(list(port)) == 1)
                    const = list(port)[0]
                    assert(const.tag == "const")
                    if const.get("from_string") == "true":
                        val = vast.StringConst(const.get("str"))
                    else:
                        val = vast.IntConst(verilog_string_to_int(const.get("name")))
                    param = vast.ParamArg(port.get("name"), val)
                    blackbox_inst_entry[1].append(param)

    def parse_net_list(self, nlst):
        netlist = list(nlst)
        self.parse_typetable(nlst.find("typetable"))
    
        self.used_varref(nlst)
        self.used_blackbox_module(nlst)
    
        iface_vars = []
        for iface in nlst.findall("iface"):
            iface_vars += self.parse_iface(iface)

        top_mod = None
        for mod in nlst.findall("module"):
            if mod.get("origName") == "TOP":
                top_mod = mod
    
        module = self.parse_module(top_mod, iface_vars)
    
        return module
    
    def parse(self):
        tree = ET.parse(self.xml_filename)
        root = tree.getroot()
        l = list(root)
        files = self.parse_files(l[0])
        module_files = self.parse_files(l[1])
        cells = self.parse_cells(l[2])
        ast = self.parse_net_list(l[3])
        return ast

verilator_arg_template = """\
{} -cc -timescale-override 10ps/10ps -Wno-WIDTH -Wno-LITENDIAN -Wno-UNPACKED -Wno-BLKANDNBLK -Wno-TIMESCALEMOD \
-Wno-CASEINCOMPLETE -Wno-CASEX -Wno-PINMISSING -trace-fst -trace-structs -assert -trace-max-array 65536 \
-trace-max-width 65536 -unroll-count 65536 --Mdir {} --flatten --xml-only --xml-opt -F {} \
-Wno-SPLITVAR -Wno-VLTAG -comp-limit-syms 0 --force-split-var {} \
--top-module {}"""

verilator_arg_template_single_file = """\
{} -cc -timescale-override 10ps/10ps -Wno-WIDTH -Wno-LITENDIAN -Wno-UNPACKED -Wno-BLKANDNBLK \
-Wno-CASEINCOMPLETE -Wno-CASEX -Wno-PINMISSING -trace-fst -trace-structs -assert -trace-max-array 65536 \
-trace-max-width 65536 -unroll-count 65536 --Mdir {} --flatten --xml-only --xml-opt {} \
-Wno-SPLITVAR -Wno-VLTAG -comp-limit-syms 0 --force-split-var {} \
--top-module {}"""

class Verilator:
    def __init__(self, top_module_name, desc_file=None, files=None, skip_opt_veq=False):
        self.top_module_name = top_module_name
        self.desc_file = desc_file
        self.files = files
        assert(self.desc_file != None or self.files != None)
        self.verilator_path = str(pathlib.Path(__file__).parent.absolute()/"verilator"/"bin"/"verilator")
        self.tempdir = tempfile.mkdtemp(prefix="veripass-")
        self.x2a = None
        self.ast = None
        self.split_v = None
        self.is_splitted = False
        self.skip_opt_veq = ""
        if skip_opt_veq:
            self.skip_opt_veq = "--skip-opt-verilog-eq"

    def compile(self):
        if self.desc_file != None:
            verilator_arg = verilator_arg_template.format(self.verilator_path,
                    self.tempdir, self.desc_file, self.skip_opt_veq, self.top_module_name)
        else:
            fls = ""
            for f in self.files:
                fls += f
                fls += " "
            verilator_arg = verilator_arg_template_single_file.format(self.verilator_path,
                    self.tempdir, fls, self.skip_opt_veq, self.top_module_name)
        print("Verilator: {}".format(self.verilator_path))
        print("Temp Dir: {}".format(self.tempdir))
        os.system(verilator_arg)

    def get_ast(self):
        self.compile()
        if self.x2a == None:
            self.x2a = VerilatorXMLToAST(self.top_module_name, self.tempdir+"/V"+self.top_module_name+".xml")
        if self.ast == None:
            self.ast = self.x2a.parse()
        return self.ast

    def get_used_vars(self):
        if self.ast == None:
            self.get_ast()
        return self.x2a.used_vars

    def get_typetable(self):
        if self.ast == None:
            self.get_ast()
        return self.x2a.typetable

    def get_splitted_ast(self):
        self.compile()
        self.x2a = VerilatorXMLToAST(self.top_module_name, self.tempdir+"/V"+self.top_module_name+".xml")
        self.x2a.split_var = True
        self.ast = self.x2a.parse()
        self.is_splitted = True

        codegen = ASTCodeGenerator()
        rslt = codegen.visit(self.ast)
        passed_v = self.tempdir+"/"+self.top_module_name+".generated.v"
        with open(passed_v, "w+") as f:
            f.write(rslt)
        self.split_v = Verilator(self.top_module_name, files=[passed_v])
        return self.split_v.get_ast()

    def get_splitted_used_vars(self):
        if self.is_splitted == False:
            self.get_splitted_ast()
        return self.split_v.get_used_vars()

    def get_splitted_typetable(self):
        if self.is_splitted == False:
            self.get_splitted_ast()
        return self.split_v.get_typetable()


#x2a = VerilatorXMLToAST("ccip_std_afu_wrapper", "/home/jcma/veripass/work/Vccip_std_afu_wrapper.xml")
#ast = x2a.parse()
#codegen = ASTCodeGenerator()
#rslt = codegen.visit(ast)
#print(rslt)

