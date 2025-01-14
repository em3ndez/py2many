from typing import Callable, Dict, List, Set, Optional
from ctypes import c_int8 as i8, c_int16 as i16, c_int32 as i32, c_int64 as i64
from ctypes import c_uint8 as u8, c_uint16 as u16, c_uint32 as u32, c_uint64 as u64
import sys


def do_unsupported():
    a: int = 1
    {key + 1: value + 1 for key, value in {}}
    b: bool = bool(a)
    print("True" if b else "False")


if __name__ == "__main__":
    do_unsupported()
