// Forward declaration fixture — no definition reachable for Bar.
// No system headers.

struct Bar;

// Pointer to incomplete type — valid C++.
Bar* create_bar();
