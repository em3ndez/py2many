import io
import os
import ast
import functools

from tempfile import NamedTemporaryFile
from typing import Callable, Dict, List, Tuple, Union

try:
    from argparse_dataclass import dataclass as ap_dataclass
    from argparse_dataclass import ArgumentParser
except:
    ArgumentParser = "ArgumentParser"
    ap_dataclass = "ap_dataclass"


class CppTranspilerPlugins:
    def visit_argparse_dataclass(self, node):
        pass

    def visit_open(self, node, vargs):
        self._usings.add("std::fs::File")
        if len(vargs) > 1:
            self._usings.add("std::fs::OpenOptions")
            mode = vargs[1]
            opts = "OpenOptions::new()"
            is_binary = "b" in mode
            for c in mode:
                if c == "w":
                    if not is_binary:
                        self._usings.add("pylib::FileWriteString")
                    opts += ".write(true)"
                if c == "r":
                    if not is_binary:
                        self._usings.add("pylib::FileReadString")
                    opts += ".read(true)"
                if c == "a":
                    opts += ".append(true)"
                if c == "+":
                    opts += ".read(true).write(true)"
            node.result_type = True
            return f"{opts}.open({vargs[0]})"
        node.result_type = True
        return f"File::open({vargs[0]})"

    def visit_named_temp_file(self, node, vargs):
        node.annotation = ast.Name(id="tempfile._TemporaryFileWrapper")
        node.result_type = True
        return "NamedTempFile::new()"

    def visit_textio_read(self, node, vargs):
        # TODO
        return None

    def visit_textio_write(self, node, vargs):
        # TODO
        return None

    def visit_ap_dataclass(self, cls):
        # Do whatever transformation the decorator does to cls here
        return cls

    def visit_range(self, node, vargs: List[str]) -> str:
        lint_exception = (
            "  // NOLINT(build/include_order)" if not self._no_prologue else ""
        )
        self._headers.append(f'#include "pycpp/runtime/range.hpp"{lint_exception}')
        args = ", ".join(vargs)
        return f"rangepp::xrange({args})"

    def visit_print(self, node, vargs: List[str]) -> str:
        self._usings.add("<iostream>")
        buf = []
        for n in node.args:
            value = self.visit(n)
            if isinstance(n, ast.List) or isinstance(n, ast.Tuple):
                buf.append(
                    "std::cout << {0};".format(
                        " << ".join([self.visit(el) for el in n.elts])
                    )
                )
            else:
                buf.append("std::cout << {0};".format(value))
            buf.append('std::cout << " ";')
        return "\n".join(buf[:-1]) + "\nstd::cout << std::endl;"

    def visit_min_max(self, node, vargs, is_max: bool) -> str:
        min_max = "max" if is_max else "min"
        t1 = self._typename_from_annotation(node.args[0])
        t2 = None
        if len(node.args) > 1:
            t2 = self._typename_from_annotation(node.args[1])
        if hasattr(node.args[0], "container_type"):
            self._usings.add("<algorithm>")
            return f"*std::{min_max}_element({vargs[0]}.begin(), {vargs[0]}.end());"
        else:
            # C++ can't deal with max(1, size_t)
            if t1 == "int" and t2 == self._default_type:
                vargs[0] = f"static_cast<size_t>({vargs[0]})"
            all_vargs = ", ".join(vargs)
            return f"std::{min_max}({all_vargs})"

    @staticmethod
    def visit_cast(node, vargs, cast_to: str) -> str:
        return f"static_cast<{cast_to}>({vargs[0]})"

    def visit_floor(node, vargs) -> str:
        return f"static_cast<size_t>(floor({vargs[0]}))"

    @staticmethod
    def visit_asyncio_run(node, vargs) -> str:
        return f"block_on({vargs[0]})"


# small one liners are inlined here as lambdas
SMALL_DISPATCH_MAP = {
    "int": lambda n, vargs: f"pycpp::to_int({vargs[0]})",
    # Is pycpp::to_int() necessary?
    # "int": functools.partial(visit_cast, cast_to="i32"),
    "str": lambda n, vargs: f"std::to_string({vargs[0]})",
    "bool": lambda n, vargs: f"static_cast<bool>({vargs[0]})",
    "len": lambda n, vargs: f"{vargs[0]}.size()",
    "float": functools.partial(CppTranspilerPlugins.visit_cast, cast_to="float"),
    "max": functools.partial(CppTranspilerPlugins.visit_min_max, is_max=True),
    "min": functools.partial(CppTranspilerPlugins.visit_min_max, is_min=True),
    "floor": CppTranspilerPlugins.visit_floor,
}

SMALL_USINGS_MAP = {
    "floor": "<math.h>",
}

DISPATCH_MAP = {
    "max": functools.partial(CppTranspilerPlugins.visit_min_max, is_max=True),
    "min": functools.partial(CppTranspilerPlugins.visit_min_max, is_min=True),
    "range": CppTranspilerPlugins.visit_range,
    "xrange": CppTranspilerPlugins.visit_range,
    "print": CppTranspilerPlugins.visit_print,
}

MODULE_DISPATCH_TABLE = {}

DECORATOR_DISPATCH_TABLE = {ap_dataclass: CppTranspilerPlugins.visit_ap_dataclass}

CLASS_DISPATCH_TABLE = {ap_dataclass: CppTranspilerPlugins.visit_argparse_dataclass}

ATTR_DISPATCH_TABLE = {
    "temp_file.name": lambda self, node, value, attr: f"{value}.path()",
}

FuncType = Union[Callable, str]

FUNC_DISPATCH_TABLE: Dict[FuncType, Tuple[Callable, bool]] = {
    # Uncomment after upstream uploads a new version
    # ArgumentParser.parse_args: lambda node: "Opts::parse_args()",
    # HACKs: remove all string based dispatch here, once we replace them with type based
    "parse_args": (lambda self, node, vargs: "::from_args()", False),
    "f.read": (lambda self, node, vargs: "f.read_string()", True),
    "f.write": (lambda self, node, vargs: f"f.write_string({vargs[0]})", True),
    "f.close": (lambda self, node, vargs: "drop(f)", False),
    open: (CppTranspilerPlugins.visit_open, True),
    NamedTemporaryFile: (CppTranspilerPlugins.visit_named_temp_file, True),
    io.TextIOWrapper.read: (CppTranspilerPlugins.visit_textio_read, True),
    io.TextIOWrapper.read: (CppTranspilerPlugins.visit_textio_write, True),
    os.unlink: (lambda self, node, vargs: f"std::fs::remove_file({vargs[0]})", True),
}
