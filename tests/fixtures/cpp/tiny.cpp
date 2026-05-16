// Minimal C++ file for libclang smoke-parse tests (Story 4).
// No system headers — libclang may not have access to sysroot in test context.

int add(int a, int b) {
    return a + b;
}

struct Point {
    int x;
    int y;
};
