import ast
from itertools import chain, izip_longest


class NotEnoughSpace(Exception):

    pass


class UnknownNodeType(Exception):

    def __init__(self, expr):
        self.expr = expr

    def __str__(self):
        attrs = ', '.join('%s=%s' % (a, getattr(self.expr, a))
                          for a in dir(self.expr)
                          if not a.startswith('_'))
        return ('Unkown expression type: %s;\n\ndir(expr) = %s\n\n'
                'attrs: %s' % (type(self.expr), dir(self.expr), attrs))

class CodeLine(object):

    INDENT = '    '

    def __init__(self, tokens=None):
        self.tokens = tokens or []

    def indent(self, indent):
        self.tokens.insert(0, indent)
        return self

    def append(self, token):
        return self.tokens.append(token)

    def extend(self, tokens):
        return self.tokens.extend(tokens)

    def __len__(self):
        return sum((len(t) for t in self.tokens))

    def __unicode__(self):
        return u''.join(self.tokens)


class CodeBlock(object):

    def __init__(self, lines=None):
        self.lines = lines or [CodeLine()]

    @classmethod
    def from_tokens(cls, *tokens):
        lines = [CodeLine(list(tokens))]
        return cls(lines)

    def extend(self, block, indent=None):
        if indent:
            self.lines.extend((CodeLine([indent] + l.tokens)
                               for l in block.lines))
        else:
            self.lines.extend((CodeLine(l.tokens)
                               for l in block.lines))
        return self

    def merge(self, block, separator=None):
        if separator:
            self.append_tokens(separator)
        lines = block.lines
        indent = len(self.lines[-1])*' '
        self.last_line.extend(block.lines[0].tokens)
        for original in lines[1:]:
            line = CodeLine([indent])
            line.extend(original.tokens)
            self.lines.append(line)
        return self

    def append_tokens(self, *tokens):
        self.last_line.extend(tokens)
        return self

    @property
    def last_line(self):
        return self.lines[-1]

    @property
    def width(self):
        return max(len(l) for l in self.lines)

    @property
    def height(self):
        return len(self.lines)

    def __unicode__(self):
        return '\n'.join(unicode(l) for l in self.lines)


class AstFormatterMetaclass(type):

    def __new__(cls, name, bases, attrs):
        klass = type.__new__(cls, name, bases, attrs)
        if attrs.get('ast_type') is not None:
            klass._n2f[attrs['ast_type']] = klass
        return klass


class AstFormatter(object):

    __metaclass__ = AstFormatterMetaclass
    _n2f = {}

    def __init__(self, expr, parent=None):
        self.expr = expr
        self.parent = parent

    def format_code(self, width, force=False):
        raise NotImplementedError()

    @classmethod
    def from_ast(cls, expr, parent=None, **extra):
        try:
            FormatterClass = cls._n2f[type(expr)]
            assert issubclass(FormatterClass, cls)
            return FormatterClass(expr, parent=parent, **extra)
        except KeyError:
            raise UnknownNodeType(expr)


class ExprFormatter(AstFormatter):

    ast_type = ast.Expr

    def __new__(cls, expr, parent):
        return cls.from_ast(expr, parent)

    @classmethod
    def from_ast(cls, expr, parent, **extra):
        return AstFormatter.from_ast(expr.value, parent, **extra)


class ExpressionFormatter(AstFormatter):

    pass


class Atom(ExpressionFormatter):

    ast_type = None

    def _format_code(self):
        raise NotImplementedError()

    def format_code(self, width, force=False):
        block = CodeBlock([CodeLine([self._format_code()])])
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class Name(Atom):

    ast_type = ast.Name

    def _format_code(self):
        return unicode(self.expr.id)


class Op(Atom):

    def _format_code(self):
        return self.operator


for ast_type, operator in [(ast.Gt, '>'), (ast.GtE, '>='),
                           (ast.Lt, '<'), (ast.LtE, '<='),
                           (ast.Eq, '=='), (ast.NotEq, '!='),
                           (ast.Is, 'is'), (ast.IsNot, 'is not'),
                           (ast.In, 'in'), (ast.NotIn, 'not in')]:
    type(ast_type.__name__, (Op,), {'ast_type': ast_type,
                                    'operator': operator})

for ast_type, operator in [(ast.Or, 'or'), (ast.And, 'and'),
                           (ast.Not, 'not')]:
    type(ast_type.__name__, (Op,), {'ast_type': ast_type,
                                    'operator': operator})

class UnaryOperand(ExpressionFormatter):

    ast_type = ast.UnaryOp
    operator = None

    def format_code(self, width, force=False):
        op_formatter = AstFormatter.from_ast(self.expr.op)
        operator = '%s' % op_formatter.operator
        separator = ' '
        value_formatter = ExpressionFormatter.from_ast(self.expr.operand)
        value_block = value_formatter.format_code(width - len(operator) -
                                                  len(separator))
        block = CodeBlock.from_tokens(operator)
        block.merge(value_block, separator=' ')
        return block


class BinOp(Op):

    priority = 0


class BinaryOperation(ExpressionFormatter):

    ast_type = ast.BinOp

    @property
    def priority(self):
        return AstFormatter.from_ast(self.expr.op, self.expr).priority

    def format_code(self, width, force=False):
        opt_formatter = AstFormatter.from_ast(self.expr.op, self.expr)
        left_formatter = ExpressionFormatter.from_ast(self.expr.left,
                                                      parent=self.expr)
        right_formatter = ExpressionFormatter.from_ast(self.expr.right,
                                                       parent=self.expr)
        def _format_code(with_brackets):
            block = CodeBlock()
            if with_brackets:
                block.append_tokens('(')
            indent = block.width*' '
            try:
                left_block = left_formatter.format_code(width-block.width)
                operator_block = opt_formatter.format_code(width - block.width -
                                                           left_block.width - 1)
                right_block = right_formatter.format_code(width - block.width -
                                                          operator_block.width - 2 -
                                                          left_block.width)
                block.merge(left_block)
                block.merge(operator_block, separator= ' ')
                block.merge(right_block, separator=' ')
            except NotEnoughSpace:
                operator = '%s' % opt_formatter.operator
                left_block = left_formatter.format_code(width - len(indent) - len(operator) - 1,
                                                        force=force)
                right_block = right_formatter.format_code(width-len(indent), force=force)
                block.merge(left_block)
                block.append_tokens(' ', operator)
                block.extend(right_block, indent)
            if with_brackets:
                block.append_tokens(')')
            return block, right_block
        with_brackets = (self.parent and
                         (isinstance(self.parent, ast.BinOp) and
                          BinaryOperation.from_ast(self.parent).priority > self.priority))

        block, right_subblock = _format_code(with_brackets)
        if not self.parent and block.height > 1 and right_subblock.height != block.height:
            block, _ = _format_code(True)
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


for ast_type, operator, priority in [(ast.Mult, '*', 1),
                                     (ast.FloorDiv, '//', 1),
                                     (ast.Div, '/', 1),
                                     (ast.Mod, '%', 1),
                                     (ast.Add, '+', 0),
                                     (ast.Sub, '-', 0)]:
    type(ast_type.__name__, (BinOp,), {'ast_type': ast_type,
                                       'operator': operator,
                                       'priority': priority})


class BooleanOperation(ExpressionFormatter):

    ast_type = ast.BoolOp

    def format_code(self, width, force=False):
        def _format_code(with_brackets):
            block = CodeBlock()
            if with_brackets:
                block.append_tokens('(')
            opt_formatter = AstFormatter.from_ast(self.expr.op, self.expr)
            value_formatter = ExpressionFormatter.from_ast(self.expr.values[0],
                                                           parent=self.expr)
            indent = block.width*' '
            block.merge(value_formatter.format_code(width - block.width,
                                                    force=force))
            for e in self.expr.values[1:]:
                value_formatter = ExpressionFormatter.from_ast(e)
                try:
                    operator_block = opt_formatter.format_code(width-2)
                    value_block = value_formatter.format_code(width -
                                                              block.width -
                                                              operator_block.width -
                                                              2)
                    block.merge(operator_block, separator=' ')
                    block.merge(value_block, separator=' ')
                except NotEnoughSpace:
                    value_block = value_formatter.format_code(width -
                                                              len(indent) -
                                                              len(operator) - 1,
                                                              force=force)
                    block.append_tokens(' ', opt_formatter.operator)
                    block.extend(value_block, indent)
            if with_brackets:
                block.append_tokens(')')
            return block, value_block
        with_brackets = (self.parent and
                         not isinstance(self.parent,
                                        (ast.For, ast.Assign)))
        block, last_subblock = _format_code(with_brackets)
        if not with_brackets and block.height > 1 and last_subblock.height != block.height:
            block, _ = _format_code(True)
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class Num(Atom):

    ast_type = ast.Num

    def _format_code(self):
        return unicode(self.expr.n)


class Str(Atom):

    ast_type = ast.Str

    def _format_code(self):
        return unicode("'%s'" % self.expr.s)


class Attribute(ExpressionFormatter):

    ast_type = ast.Attribute

    def format_code(self, width, force=False):
        block = ExpressionFormatter.from_ast(self.expr.value,
                                              self.expr).format_code(width-len(self.expr.attr)-1,
                                                                     force=force)
        return block.append_tokens('.', self.expr.attr)


def format_list_of_expressions(expressions, width, force=False):
    curr_line = CodeLine([])
    block = CodeBlock([curr_line])

    for param, expr in enumerate(expressions):
        try:
            free_space = width - len(block.lines[-1])
            if param > 0:
                separator = ', '
                free_space = free_space - len(separator)
            subblock = expr.format_code(free_space, force=param==0)
            if param > 0:
                curr_line.append(separator)
            block.merge(subblock)
        except NotEnoughSpace:
            subblock = expr.format_code(width, force=True)
            curr_line.append(',')
            block.extend(subblock)
        curr_line = block.lines[-1]
        if not force and block.width > width:
            raise NotEnoughSpace()
    return block


class Call(ExpressionFormatter):

    ast_type = ast.Call

    class KeywordArg(ExpressionFormatter):

        ast_type = ast.keyword

        def format_code(self, width, force=False):
            block = CodeBlock([CodeLine(['%s=' % self.expr.arg])])
            expression_formatter = ExpressionFormatter.from_ast(self.expr.value, self.expr)
            expression_block = expression_formatter.format_code(width - block.width,
                                                                force=force)
            block.merge(expression_block)
            return block

    class StarArgsFormatter(object):

        def __init__(self, subexpression, prefix):
            self.subexpression = subexpression
            self.prefix = prefix

        def format_code(self, width, force=False):
            block = CodeBlock.from_tokens(self.prefix)
            subexpression_formatter = ExpressionFormatter.from_ast(self.subexpression)
            block.merge(subexpression_formatter.format_code(width - block.width,
                                                            force=force))
            return block


    def format_code(self, width, force=False):
        block = ExpressionFormatter.from_ast(self.expr.func).format_code(width, force=force)
        block.lines[-1].append('(')
        expressions = [ExpressionFormatter.from_ast(e, self.expr) for e in self.expr.args]
        if self.expr.starargs:
            expressions.append(Call.StarArgsFormatter(self.expr.starargs, '*'))
        expressions += [ExpressionFormatter.from_ast(e, self.expr) for e in self.expr.keywords]
        if self.expr.kwargs:
            expressions.append(Call.StarArgsFormatter(self.expr.kwargs, '**'))
        subblock = format_list_of_expressions(expressions, width-block.width, force=force)
        block.merge(subblock)
        block.lines[-1].append(')')
        return block


class DictFormatter(ExpressionFormatter):

    ast_type = ast.Dict

    class Item(ExpressionFormatter):

        def __init__(self, key, value, parent):
            self.key = ExpressionFormatter.from_ast(key, parent)
            self.value = ExpressionFormatter.from_ast(value, parent)

        def format_code(self, width, force=False):
            # FIXME: search for solution on failure
            separator = ':'
            block = self.key.format_code(width-len(separator)-1,
                                         force=force)
            block.lines[-1].append(separator)
            block.merge(self.value.format_code(width-block.width,
                                               force=force), separator=' ')
            return block

    def format_code(self, width, force=False):
        block = CodeBlock([CodeLine(['{'])])
        expressions = [DictFormatter.Item(k, v, self.expr)
                       for k, v in zip(self.expr.keys,
                                       self.expr.values)]
        subblock = format_list_of_expressions(expressions=expressions,
                                              width=width-block.width, force=force)
        block.merge(subblock)
        block.lines[-1].append('}')
        return block


class ListFormatter(ExpressionFormatter):

    ast_type = ast.List

    def format_code(self, width, force=False):
        block = CodeBlock([CodeLine(['['])])
        expressions = [ExpressionFormatter.from_ast(v, self.expr)
                       for v in self.expr.elts]
        subblock = format_list_of_expressions(expressions=expressions,
                                              width=width-block.width,
                                              force=force)
        block.merge(subblock)
        block.lines[-1].append(']')
        return block


class ListComprehensionFormatter(ExpressionFormatter):

    ast_type = ast.ListComp

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('[')
        indent = block.width * ' '
        elt_formatter = ExpressionFormatter.from_ast(self.expr.elt,
                                                     parent=self.expr)
        elt_block = elt_formatter.format_code(width - block.width,
                                              force=force)
        block.merge(elt_block)
        try:
            generators_block = format_generators(self.expr.generators,
                                                 width - block.width - 1,
                                                 parent=self.expr)
            block.merge(generators_block, separator=' ')
        except NotEnoughSpace:
            generators_block = format_generators(self.expr.generators,
                                                 width - len(indent),
                                                 parent=self.expr,
                                                 force=force)
            block.extend(generators_block, indent)
        block.append_tokens(']')
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class SetFormatter(ExpressionFormatter):

    ast_type = ast.Set

    def format_code(self, width, force=False):
        block = CodeBlock([CodeLine(['{'])])
        expressions = [ExpressionFormatter.from_ast(v, self.expr)
                       for v in self.expr.elts]
        subblock = format_list_of_expressions(expressions=expressions,
                                              width=width-block.width,
                                              force=force)
        block.merge(subblock)
        block.lines[-1].append('}')
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class SetComprehensionFormatter(ExpressionFormatter):

    ast_type = ast.SetComp

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('{')
        indent = block.width * ' '
        elt_formatter = ExpressionFormatter.from_ast(self.expr.elt,
                                                     parent=self.expr)
        elt_block = elt_formatter.format_code(width - block.width,
                                              force=force)
        block.merge(elt_block)
        try:
            generators_block = format_generators(self.expr.generators,
                                                 width - block.width - 1,
                                                 parent=self.expr)
            block.merge(generators_block, separator=' ')
        except NotEnoughSpace:
            generators_block = format_generators(self.expr.generators,
                                                 width - len(indent),
                                                 parent=self.expr,
                                                 force=force)
            block.extend(generators_block, indent)
        block.append_tokens('}')
        return block


class IfExpression(ExpressionFormatter):

    ast_type = ast.IfExp

    def format_code(self, width, force=False):
        body_formatter = ExpressionFormatter.from_ast(self.expr.body,
                                                      parent=self.expr)
        block = body_formatter.format_code(width, force=force)
        test_formatter = ExpressionFormatter.from_ast(self.expr.test,
                                                      parent=self.expr)
        block.append_tokens(' ', 'if', ' ')
        test_block = test_formatter.format_code(width-block.width, force=force)
        block.merge(test_block)
        orelse_formatter = ExpressionFormatter.from_ast(self.expr.orelse,
                                                        parent=self.expr)
        block.append_tokens(' ', 'else', ' ')
        orelse_block = orelse_formatter.format_code(width - block.width,
                                                    force=force)
        block.merge(orelse_block)
        return block


class Subscription(ExpressionFormatter):

    ast_type = ast.Subscript

    def format_code(self, width, force=False):
        value_formatter = ExpressionFormatter.from_ast(self.expr.value, self.expr)
        block = value_formatter.format_code(width, force=force)
        block.lines[-1].append('[')
        index_formatter = ExpressionFormatter.from_ast(self.expr.slice.value, self.expr)
        block.merge(index_formatter.format_code(width - len(block.lines[-1]) - 1,
                                                force=force))
        block.lines[-1].append(']')
        return block


class Sice(ExpressionFormatter):

    ast_type = ast.Slice

    def format_code(self, width, force=False):
        pass


class Compare(ExpressionFormatter):

    ast_type = ast.Compare

    def format_code(self, width, force=False):
        block = ExpressionFormatter.from_ast(self.expr.left).format_code(width, force=force)
        for operator, comparator in zip(self.expr.ops, self.expr.comparators):
            block.merge(ExpressionFormatter.from_ast(operator).format_code(width-block.width-1,
                                                                            force=force), separator=' ')
            block.merge(ExpressionFormatter.from_ast(comparator).format_code(width-block.width,
                                                                              force=force), separator=' ')
        return block


class Generator(ExpressionFormatter):

    ast_type = ast.GeneratorExp

    def __init__(self, expr, parent=None):
        self.expr = expr
        self.parent = parent

    def format_code(self, width, force=False):
        value_formatter = ExpressionFormatter.from_ast(self.expr.elt, self.expr)
        with_brackets = (not self.parent or not isinstance(self.parent, ast.Call) or
                         len(self.parent.args) != 1)
        if with_brackets:
            block = CodeBlock([CodeLine(['('])])
            indent = block.width * ' '
            block.merge(value_formatter.format_code(width, force=force))
        else:
            indent = ''
            block = value_formatter.format_code(width, force=force)
        try:
            generators_block = format_generators(self.expr.generators,
                                                 width - block.width - 1,
                                                 parent=self.expr)
            block.merge(generators_block, separator=' ')
        except NotEnoughSpace:
            generators_block = format_generators(self.expr.generators,
                                                 width - len(indent),
                                                 parent=self.expr,
                                                 force=force)
            block.extend(generators_block, indent)

        if with_brackets:
            block.append_tokens(')')
        # FIXME: raise exception
        return block


def format_generators(generators, width, parent, force=False):
    block = CodeBlock()
    for generator_number, generator in enumerate(generators):
        target_formatter = ExpressionFormatter.from_ast(generator.target,
                                                        parent=parent)
        iter_formatter = ExpressionFormatter.from_ast(generator.iter,
                                                      parent=parent)
        ifs_formatters = [ExpressionFormatter.from_ast(if_, parent=parent)
                          for if_ in generator.ifs]

        formatters = chain([(target_formatter, 'for'), (iter_formatter, 'in')],
                           izip_longest(ifs_formatters, (), fillvalue='if'))
        for part, (formatter, keyword) in enumerate(formatters, generator_number):
            try:
                spaces_count = 2 if part > 0 else 1
                formatter_block = formatter.format_code(width -
                                                        len(block.last_line) -
                                                        len(keyword) -
                                                        spaces_count)
                if part > 0:
                    block.append_tokens(' ', keyword)
                else:
                    block.append_tokens(keyword)
                block.merge(formatter_block, separator=' ')
            except NotEnoughSpace:
                formatter_block = formatter.format_code(width - len(keyword) - 1,
                                                        force=force)
                block.lines.append(CodeLine([keyword]))
                block.merge(formatter_block, separator=' ')
    return block


class DictComprehension(ExpressionFormatter):

    ast_type = ast.DictComp

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('{')
        indent = block.width * ' '
        key_formatter = ExpressionFormatter.from_ast(self.expr.key,
                                                     parent=self.expr)
        value_formatter = ExpressionFormatter.from_ast(self.expr.value,
                                                       parent=self.expr)
        separator = ': '
        key_block = key_formatter.format_code(width - block.width - len(separator),
                                              force=force)
        value_block = value_formatter.format_code(width - block.width -
                                                  len(separator), force=force)
        block.merge(key_block)
        block.append_tokens(separator)
        block.merge(value_block)

        try:
            generators_block = format_generators(self.expr.generators,
                                                 width - block.width - 1,
                                                 parent=self.expr)
            block.merge(generators_block, separator=' ')
        except NotEnoughSpace:
            generators_block = format_generators(self.expr.generators,
                                                 width - len(indent),
                                                 parent=self.expr,
                                                 force=force)
            block.extend(generators_block, indent)
        block.append_tokens('}')
        return block


class Tuple(ExpressionFormatter):

    ast_type = ast.Tuple

    def format_code(self, width, force=False):
        with_brackets = (isinstance(self.parent, (ast.Tuple, ast.Call,
                                                  ast.List, ast.BinOp,
                                                  ast.ListComp)) or
                         len(self.expr.elts) < 2)
        block = CodeBlock()
        expressions = [ExpressionFormatter.from_ast(v, self.expr)
                       for v in self.expr.elts]
        if with_brackets:
            block.append_tokens('(')
        expression_block = format_list_of_expressions(expressions,
                                                      width-block.width,
                                                      force=force)
        if expression_block.height > 1 and not with_brackets:
            block.append_tokens('(')
            with_brackets = True
            expression_block = format_list_of_expressions(expressions,
                                                          width-block.width,
                                                          force=force)
        block.merge(expression_block)
        # FIXME: to be 'super' consistent we should check last line
        #        and enforce reformatting... or change API somehow
        if len(self.expr.elts) == 1:
            block.append_tokens(',')
        if with_brackets:
            block.append_tokens(')')
        return block


class ParameterListFormatter(AstFormatter):

    ast_type = ast.arguments

    def format_code(self, width, force=False):
        block = CodeBlock()
        for n, arg in enumerate(self.expr.args):
            # FIXME: move to next line
            arg_formatter = AstFormatter.from_ast(arg)
            try:
                arg_block = arg_formatter.format_code(width - block.width - 2,
                                                      force=False)
                if n > 0:
                    block.append_tokens(',', ' ')
                block.merge(arg_block)
            except NotEnoughSpace:
                if n > 0:
                    block.append_tokens(',')
                arg_block = arg_formatter.format_code(width, force=force)
                block.extend(arg_block)
        return block


class LambdaFormatter(ExpressionFormatter):

    ast_type = ast.Lambda

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('lambda')
        parameter_list_formatter = AstFormatter.from_ast(self.expr.args)
        parameter_list_block = parameter_list_formatter.format_code(width-block.width)
        if parameter_list_block.width > 0:
            block.append_tokens(' ')
            block.merge(parameter_list_formatter.format_code(width-block.width))
        block.append_tokens(':', ' ')
        subexpression_formatter = AstFormatter.from_ast(self.expr.body)
        block.merge(subexpression_formatter.format_code(width - block.width,
                                                        force=force))
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class StatementFormatter(AstFormatter):

    pass


class PassFormatter(StatementFormatter):

    ast_type = ast.Pass

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('pass')
        if not force and block.width > width:
            raise NotEnoughSpace
        return block


class ReturnFormatter(StatementFormatter):

    ast_type = ast.Return

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('return')
        expression_formatter = ExpressionFormatter.from_ast(self.expr.value)
        expression_block = expression_formatter.format_code(width -
                                                            block.width - 1,
                                                            force=force)
        block.merge(expression_block, separator=' ')
        if not force and block.width > width:
            raise NotEnoughSpace
        return block


class ImportFormatterBase(StatementFormatter):

    class AliasFormatter(StatementFormatter):

        ast_type = ast.alias

        @property
        def name(self):
            return self.expr.name

        def format_code(self, width, force=False):
            block = CodeBlock.from_tokens(self.expr.name)
            if self.expr.asname:
                block.append_tokens('as', ' ', self.expr.asname)
            if not force and block.width > width:
                raise NotEnoughSpace()
            return block

    def format_aliases(self, width, force):
        block = CodeBlock()
        aliases = sorted([ImportFormatterBase.AliasFormatter.from_ast(alias)
                          for alias in self.expr.names], key=lambda a: a.name.lower())
        aliases_block = format_list_of_expressions(aliases, width,
                                                   force)
        if aliases_block.height > 1:
            block.append_tokens('(')
            aliases_block = format_list_of_expressions(aliases, width-block.width,
                                                       force=force)
            block.merge(aliases_block)
            block.append_tokens(')')
        else:
            block.merge(aliases_block)
        return block


class ImportFormatter(ImportFormatterBase):

    ast_type = ast.Import

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('import', ' ')
        block.merge(self.format_aliases(width-block.width, force=force))
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class ImportFromFormatter(ImportFormatterBase):

    ast_type = ast.ImportFrom

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('from', ' ', self.expr.module, ' ', 'import', ' ')
        block.merge(self.format_aliases(width-block.width, force=force))
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class ForFormatter(StatementFormatter):

    ast_type = ast.For

    def format_code(self, width, force=False):
        in_ = 'in'
        block = CodeBlock([CodeLine(['for'])])
        target_formatter = ExpressionFormatter.from_ast(self.expr.target,
                                                        self.expr)
        block.merge(target_formatter.format_code(width - block.width - len(in_) - 1,
                                                 force=force), separator=' ')
        block.append_tokens(' ', in_)
        iter_formatter = ExpressionFormatter.from_ast(self.expr.iter, self.expr)
        block.merge(iter_formatter.format_code(width - block.width - 1,
                                               force=force), separator=' ')
        block.append_tokens(':')
        for a in self.expr.body:
            formatter = AstFormatter.from_ast(a)
            block.extend(formatter.format_code(width-len(CodeLine.INDENT),
                                               force=force), CodeLine.INDENT)
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class AssignmentFormatter(StatementFormatter):

    ast_type = ast.Assign

    def format_code(self, width, force=False):
        block = CodeBlock()
        for target in self.expr.targets:
            target_formatter = ExpressionFormatter.from_ast(target,
                                                            parent=self.expr)

            block.merge(target_formatter.format_code(width - block.width - 3,
                                                     force=force))
            block.append_tokens(' = ')
        value_formatter = ExpressionFormatter.from_ast(self.expr.value, self.expr)
        block.merge(value_formatter.format_code(width - block.width,
                                                force=force))
        return block


class FunctionDefinitionFormatter(StatementFormatter):

    ast_type = ast.FunctionDef

    def format_code(self, width, force=False):
        block = CodeBlock.from_tokens('def', ' ', self.expr.name, '(')
        parameter_list_formatter = AstFormatter.from_ast(self.expr.args)
        # FIXME: this will be precise formatting when we move to new
        #        format_code API: format_code(block_width, first_line_width=None,
        #                                     suffix=None, force=False):
        block.merge(parameter_list_formatter.format_code(width-block.width))
        block.append_tokens('):')
        for subexpression in self.expr.body:
            subexpression_formatter = AstFormatter.from_ast(subexpression)
            block.extend(subexpression_formatter.format_code(width - len(CodeLine.INDENT),
                                                             force=force), CodeLine.INDENT)
        if not force and block.width > width:
            raise NotEnoughSpace()
        return block


class KandRAstFormatter(AstFormatter):

    _n2f = dict(AstFormatter._n2f)


class KandRDict(KandRAstFormatter, DictFormatter):

    def format_code(self, width, force=False):
        block = CodeBlock([CodeLine(['{'])])
        expressions = [DictFormatter.Item(k, v, self.expr)
                       for k, v in zip(self.expr.keys,
                                       self.expr.values)]
        subblock = format_list_of_expressions(expressions=expressions,
                                              width=width-block.width, force=force)
        block.merge(subblock)
        block.lines[-1].append('}')
        return block



def _format_code(code, width=80, AstFormatter=AstFormatter):
    tree = ast.parse(code)
    result = []
    for e in tree.body:
        formatter = AstFormatter.from_ast(e)
        result.append(formatter.format_code(width, force=True))
    return result

def format_code(code, width=80, AstFormatter=AstFormatter):
    result = _format_code(code, width, AstFormatter=AstFormatter)
    unicode(result[0])
    return u'\n'.join(unicode(e) for e in result)
