// Fixture that includes a missing header (generates parse warnings/errors)
// but still has recoverable AST content.
// Used by SC-US-4-6.

#include "this_header_does_not_exist_xyz.h"

int recoverable_function(int x) {
    return x + 1;
}

struct RecoverableStruct {
    int a;
    int b;
};
