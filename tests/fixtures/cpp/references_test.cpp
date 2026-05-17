// Fixture for get_references BDD tests.
// No system headers.

int calculate(int a, int b) {
    return a + b;
}

int main() {
    int r1 = calculate(1, 2);
    int r2 = calculate(3, 4);
    int r3 = calculate(r1, r2);
    return r3;
}
