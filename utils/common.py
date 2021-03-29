import pyverilog.vparser.ast as vast

# This is inspired by pyverilog.dataflow.visit.NodeVisitor
class ASTNodeVisitor(object):
    def __init__(self, fallback=None):
        # for debugging purpose
        self.stack = []
        self.fallback = fallback

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
        elif self.fallback:
            ret = self.fallback(node)
        else:
            raise NotImplementedError("Cannot find a call back")
        self.stack.pop()
        return ret

    def visit_children(self, node):
        for c in node.children():
            self.visit(c)
