"""Pretty-Print SQL queries for console output."""

from logging import Formatter

from django.conf import settings


class SQLFormatter(Formatter):
    """Color code with pygments, format with sqlparse."""

    def format(self, record):
        """Do the formatting."""
        # Check if Pygments is available for coloring
        try:
            import pygments
            from pygments.lexers import SqlLexer
            from pygments.formatters import TerminalTrueColorFormatter
        except ImportError:
            pygments = None

        # Check if sqlparse is available for indentation
        try:
            import sqlparse
        except ImportError:
            sqlparse = None

        # Remove leading and trailing whitespaces
        sql = record.sql.strip()

        if sqlparse:
            # Indent the SQL query
            sql = sqlparse.format(
                sql,
                wrap_after=settings.CONSOLE_WIDTH,
                indent_width=settings.CONSOLE_INDENT,
                output_format="python",
            )

        if pygments:
            # Highlight the SQL query
            sql = pygments.highlight(
                sql, SqlLexer(), TerminalTrueColorFormatter(style="monokai")
            )

        # Set the record's statement to the formatted query
        record.statement = sql
        return super(SQLFormatter, self).format(record)
