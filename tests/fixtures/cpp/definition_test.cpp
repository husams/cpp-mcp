// Fixture for cpp_get_definition and cpp_get_references BDD tests.
// No system headers — libclang may not have sysroot in test context.

int foo(int a, int b) {
    return a + b;
}

struct Point {
    int x;
    int y;
};

// unused_fn is intentionally never called — used for zero-references test.
int unused_fn() {
    return 99;
}

int main() {
    Point p;
    p.x = foo(1, 2);
    return 0;
}
