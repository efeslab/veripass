import sys
import os
import math
import tempfile
import pathlib
sys.path.append(str(pathlib.Path(__file__).parent.absolute()/"Pyverilog"))
import pyverilog.vparser.ast as vast
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator
import xml.etree.ElementTree as ET

class dtype:
    def __init__(self, width, array_len, type_name):
        self.width = width
        self.array_len = array_len
        self.type_name = type_name

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

class VerilatorXMLToAST:
    def __init__(self, top_module_name, xml_filename):
        self.top_module_name = top_module_name
        self.xml_filename = xml_filename
        self.typetable = {} # dtype_id -> dtype()
        self.used_vars = {} # var_name -> variable()

        self.parser_stack = []
    
    def name_format(self, name):
        s = name
        s = s.replace("__05F", "_")
        s = s.replace("TOP.", "", 1)
        s = s.replace(self.top_module_name+".", "", 1)
        s = s.replace(".", "__DOT__")
        s = s.replace("[", "__BRA__")
        s = s.replace("]", "__KET__")
        return s

    def verilog_string_to_int(self, s):
        value_pos = s.find("h")
        if value_pos >= 0:
            return int("0x"+s[value_pos+1:], 16)
        else:
            value_pos = s.find("b")
            if value_pos >= 0:
                return int("0b"+s[value_pos+1:], 16)
            else:
                value_pos = s.find("'")
                assert(value_pos == -1)
                return int(s)

    
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
                    assert(right == 0)
                    assert(left >= 0)
                    width = sub_dtype.width
                    array_len = left - right + 1
                    if t.tag == "unpackarraydtype":
                        self.typetable[type_id] = dtype(width, array_len, sub_dtype.type_name)
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
                    assert(right == 0)
                    width = left - right + 1
                    array_len = 0 # 0 means it is not an array
                    self.typetable[type_id] = dtype(width, array_len, type_type)
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
    
    def parse_elem_varref(self, elem):
        assert(elem.tag == "varref")
        var_name = self.name_format(elem.get("hier"))
        var_dtype = self.typetable[self.used_vars[var_name].dtype_id]
        r = vast.Identifier(self.name_format(elem.get("hier")))
        self.used_vars[var_name].ref.append(r)

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
    
        #print(start.__class__)
        #print(start.__class__ == vast.IntConst)
    
        if start.__class__ == vast.IntConst:
            start_value_pos = start.value.find("h")
            assert(start_value_pos != -1)
            start_value = self.verilog_string_to_int(start.value)
            assert(start_value == int("0x"+start.value[start_value_pos+1:], 16))
            width_value_pos = width.value.find("h")
            assert(width_value_pos != -1)
            width_value = self.verilog_string_to_int(width.value)
            assert(width_value == int("0x"+width.value[width_value_pos+1:], 16))
            msb = start_value + width_value - 1
            lsb = start_value
            r = vast.Partselect(varref, vast.IntConst(str(msb)), vast.IntConst(str(lsb)))
        else:
            width_value_pos = width.value.find("h")
            assert(width_value_pos != -1)
            width_value = self.verilog_string_to_int(width.value)
            assert(width_value == int("0x"+width.value[width_value_pos+1:], 16))
            if width_value == 1:
                r = vast.Partselect(varref, start, start)
            else:
                r = vast.Partselect(varref,
                        vast.Plus(start, vast.IntConst(str(width_value-1))),
                        start)

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
                        assert(r.lsb.__class__ == vast.Arrayselect or r.lsb.__class__ == vast.Partselect
                                or r.lsb.__class__ == vast.Identifier)
                        for i in range(0, var_dtype.width):
                            assert(self.used_vars[varref.name].dff[i] == isdff or
                                    self.used_vars[varref.name].dff[i] == None)
                            self.used_vars[varref.name].dff[i] = isdff
            elif varref.__class__ == vast.Arrayselect:
                arr = varref.var
                idx = varref.idx
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
                            value = self.verilog_string_to_int(idx.value)
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
                        assert(r.lsb.__class__ == vast.Arrayselect or r.lsb.__class__ == vast.Partselect
                                or r.lsb.__class__ == vast.Identifier)
                        if idx.__class__ == vast.IntConst:
                            value_pos = idx.value.find("h")
                            assert(value_pos != -1)
                            value = self.verilog_string_to_int(idx.value)
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

        return vast.Substitution(vast.Lvalue(left), vast.Rvalue(right))
    
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
        return vast.Plus(a, b)
    
    def parse_elem_sub(self, elem):
        assert(elem.tag == "sub")
        l = list(elem)
        assert(len(l) == 2)
        a = self.parse_elem(l[0])
        b = self.parse_elem(l[1])
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
    
    def parse_elem_not(self, elem):
        assert(elem.tag == "not")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        return vast.Unot(a)
    
    def parse_elem_extend(self, elem):
        assert(elem.tag == "extend")
        l = list(elem)
        assert(len(l) == 1)
        a = self.parse_elem(l[0])
        width = elem.get("width")
        return vast.Cast(a, width)
    
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
        return vast.Concat(items)
    
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
                args[0] = vast.StringConst(fmt.replace("%m", "%s"))
            args.append(self.parse_elem(arg))
        return vast.SingleStatement(vast.SystemCall("display", args))
    
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
                    value = self.verilog_string_to_int(idx.value)
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
                else:
                    assert(0 and "meh")

        return vast.Arrayselect(arr, idx)
    
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
        if_else = []
        for i in range(1+ifs_cnt, 1+ifs_cnt+elses_cnt):
            #print("----", i)
            if_else.append(self.parse_elem(l[i]))
        if_branch = vast.Block(if_then)
        if len(if_else) == 1 and if_else[0].__class__ == vast.IfStatement:
            else_branch = if_else[0]
        elif len(if_else) > 0:
            else_branch = vast.Block(if_else)
        else:
            else_branch = None
        return vast.IfStatement(if_cond, if_branch, else_branch)
    
    def parse_assign(self, assign):
        l = list(assign)
        self.parser_stack[-1] = "assign:right"
        right = self.parse_elem(l[0])
        self.parser_stack[-1] = "assign:left"
        left = self.parse_elem(l[1])
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
        self.parser_stack.pop()
        return items
    
    def parse_always(self, always, senslist):
        items = []
        self.parser_stack.append("always")
        for elem in list(always):
            items.append(self.parse_elem(elem))
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
                assert (assign.tag != "assignalias")
                #if assign.tag == "assignalias":
                #    continue
                #assert(assign.tag == "assign" or assign.tag == "contassign")
                senslist = vast.SensList([vast.Sens(vast.Identifier(""), type="all")])
                if assign.tag == "assign" or assign.tag == "contassign":
                    self.parser_stack.append("assign")
                    items.append(self.parse_assign(assign))
                    self.parser_stack.pop()
                elif assign.tag == "always":
                    items.append(self.parse_always(assign, senslist))
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
    
        for var in module.findall("var"):
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
                width = vast.Width(vast.IntConst(str(var_type_width-1)), vast.IntConst(str(0)))
            if var_type_array_len != 0:
                dim = vast.Width(vast.IntConst(str(var_type_array_len-1)), vast.IntConst(str(0)))
    
            if var_dir == "input":
                assert(dim == None)
                p = vast.Ioport(vast.Input(var_name, width=width), vast.Logic(var_name, width=width))
                ports.append(p)
            elif var_dir == "output":
                assert(dim == None)
                p = vast.Ioport(vast.Output(var_name, width=width), vast.Logic(var_name, width=width))
                ports.append(p)
            else:
                assert(var_dir == None)
                if var.get("param") == "true":
                    l = list(var)
                    assert(len(l) == 1 and l[0].tag == "const")
                    p = vast.Parameter(var_name, self.parse_elem(l[0]))
                    items.append(p)
                elif var_type_name == "logic":
                    p = vast.Logic(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "int":
                    p = vast.Int(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "integer":
                    p = vast.Integer(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "reg":
                    p = vast.Reg(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "wire":
                    p = vast.Wire(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "time":
                    p = vast.Time(var_name)
                    items.append(p)
                else:
                    assert(0)
        params = vast.Paramlist(params)
        ports = vast.Portlist(ports)
    
        items += iface_vars
    
        for active in module.find("topscope").find("scope").findall("active"):
            items += self.parse_active(active)
    
    
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
                    width = vast.Width(vast.IntConst(str(var_type_width-1)), vast.IntConst(str(0)))
                if var_type_array_len != 0:
                    dim = vast.Width(vast.IntConst(str(var_type_array_len-1)), vast.IntConst(str(0)))
    
                assert(var_dir == None)
                if var.get("param") == "true":
                    l = list(var)
                    assert(len(l) == 1 and l[0].tag == "const")
                    p = vast.Parameter(var_name, self.parse_elem(l[0]))
                    items.append(p)
                elif var_type_name == "logic":
                    p = vast.Logic(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "int":
                    p = vast.Int(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "integer":
                    p = vast.Integer(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "reg":
                    p = vast.Reg(var_name, width=width, dimensions=dim)
                    items.append(p)
                elif var_type_name == "wire":
                    p = vast.Wire(var_name, width=width, dimensions=dim)
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
    
    def parse_net_list(self, nlst):
        netlist = list(nlst)
        self.parse_typetable(nlst.find("typetable"))
    
        self.used_varref(nlst)
    
        iface_vars = []
        for iface in nlst.findall("iface"):
            iface_vars += self.parse_iface(iface)
    
        assert(netlist[0].tag == "module")
        module = self.parse_module(netlist[0], iface_vars)
    
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
{} -cc -timescale-override 10ps/10ps -Wno-WIDTH -Wno-LITENDIAN -Wno-UNPACKED -Wno-BLKANDNBLK \
-Wno-CASEINCOMPLETE -Wno-CASEX -Wno-PINMISSING -trace-fst -trace-structs -assert -trace-max-array 65536 \
-trace-max-width 65536 -unroll-count 65536 --Mdir {} --flatten --xml-only --xml-opt -F {} \
--top-module {}"""

class Verilator:
    def __init__(self, top_module_name, desc_file):
        self.top_module_name = top_module_name
        self.desc_file = desc_file
        self.verilator_path = str(pathlib.Path(__file__).parent.absolute()/"verilator"/"bin"/"verilator")
        self.tempdir = tempfile.mkdtemp(prefix="veripass-")
        self.x2a = None
        self.ast = None

    def compile(self):
        verilator_arg = verilator_arg_template.format(self.verilator_path,
                self.tempdir, self.desc_file, self.top_module_name)
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
            get_ast()
        return self.x2a.used_vars

    def get_typetable(self):
        if self.ast == None:
            get_ast()
        return self.x2a.typetable

#v = Verilator(top_module_name="ccip_std_afu_wrapper",
#        desc_file="/home/jcma/hardware-bugbase-final/grayscale-fifo-overflow/sources.txt")
#ast = v.get_ast()
#codegen = ASTCodeGenerator()
#rslt = codegen.visit(ast)
#print(rslt)

