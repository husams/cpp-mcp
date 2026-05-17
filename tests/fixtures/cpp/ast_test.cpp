// Fixture for get_ast BDD tests (Story 6).
// No system headers — libclang may not have access to sysroot in test context.
// 50 lines with ~5 nesting levels.

namespace outer {

namespace inner {

struct Base {
    int value;

    Base() : value(0) {}

    virtual int compute(int x) {
        return x + value;
    }

    virtual ~Base() {}
};

struct Derived : Base {
    int factor;

    Derived(int f) : factor(f) {
        value = f * 2;
    }

    int compute(int x) override {
        if (x > 0) {
            int result = x * factor;
            return result + value;
        } else {
            return value;
        }
    }
};

int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    int result = 0;
    for (int i = 0; i < b; i++) {
        result = add(result, a);
    }
    return result;
}

}  // namespace inner

}  // namespace outer
