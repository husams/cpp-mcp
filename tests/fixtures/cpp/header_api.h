// Fixture for cpp_get_header_info BDD tests (Story 6).
// Header that includes another header and exports symbols.
// No system headers.

#include "header_standalone.h"

struct ApiStruct {
    int id;
    int value;
};

int api_function(int x);

typedef int ApiInt;
