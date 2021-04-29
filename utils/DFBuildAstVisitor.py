import pyverilog.vparser.ast as vast

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
