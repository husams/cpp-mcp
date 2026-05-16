// Caller fixture for cross-file definition tests.
// References lib_func declared in lib.h.
// Compiled together so libclang resolves the declaration.

// Forward-declare to avoid including lib.h (which may not exist in isolation).
int lib_func(int x);

int main() {
    return lib_func(42);
}
