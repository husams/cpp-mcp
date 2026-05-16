// Fixture with an unresolvable include — generates a missing_includes entry.
// Used by SC-US-5-3.

#include "nonexistent_lib_12345.h"

int func_using_missing(int x);
