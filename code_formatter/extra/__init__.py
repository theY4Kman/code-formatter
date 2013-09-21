from .. import base
from ..code import CodeLine
from ..exceptions import NotEnoughSpace


class UnbreakableListOfExpressionFormatter(base.ListOfExpressionsFormatter):

    def _format_code(self, width, suffix, line_width=None):
        line_width = line_width or width
        return self._format_line_continuation(width, suffix, line_width)


class LinebreakingListOfExpressionFormatter(base.ListOfExpressionsFormatter):

    def _format_code(self, width, suffix, line_width=None):
        return self._format_line_break(width, suffix, line_width or width)


class UnbreakableTupleFormatter(base.TupleFormatter):

    ListOfExpressionsFormatter = UnbreakableListOfExpressionFormatter


class CallFormatterWithLineBreakingFallback(base.CallFormatter):

    formatable = True

    def _format_code(self, width, suffix):
        try:
            return super(CallFormatterWithLineBreakingFallback, self)._format_code(width, suffix)
        except NotEnoughSpace:
             if not self._arguments_formatters:
                raise
        suffix = self._extend_suffix(suffix, ')')
        for i in range(width+1):
            curr_width = width - i
            block = self._func_formatter.format_code(curr_width)
            block.append_tokens('(')
            try:
                subblock = self._arguments_formatter.format_code(width -
                                                                 len(CodeLine.INDENT),
                                                                 suffix=suffix)
            except NotEnoughSpace:
                continue
            else:
                # FIXME: this is really ugly way to detect last method access subexpression
                indent = max(unicode(block.last_line).rfind('.'), 0) + len(CodeLine.INDENT)
                block.extend(subblock, indent=indent)
                break
        return block
