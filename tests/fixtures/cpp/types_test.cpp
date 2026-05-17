// Fixture for get_type_info BDD tests.
// No system headers — uses only built-in types and homegrown template.

// Line 6: int variable
int x = 42;

// Line 9: auto-typed variable (resolves to float)
auto val = 3.14f;

// Homegrown template — no STL headers needed.
// Covers US-3/AC-3 (template instantiation shows expanded type).
template<typename T>
struct Box {
    T value;
};

// Line 18: template instantiation
Box<int> b;

// Incomplete type
struct Opaque;

// Line 23: pointer to incomplete type
Opaque* p_opaque;
