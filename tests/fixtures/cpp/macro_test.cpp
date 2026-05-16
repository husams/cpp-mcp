// Macro fixture for edge-case tests.
// No system headers.

#define MY_MACRO(x) ((x) + 1)
#define ANSWER 42

int use_macro() {
    return MY_MACRO(10);
}

int get_answer() {
    return ANSWER;
}
