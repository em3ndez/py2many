// generated by py2many --dlang=1
import std;
import std.algorithm;

bool nested_containers() {
  int[][string] CODES = ["KEY": [1, 3]];
  return CODES["KEY"].canFind(1);
}

void main(string[] argv) {

  if (nested_containers()) {
    writeln(format("%s", "OK"));
  }
}
