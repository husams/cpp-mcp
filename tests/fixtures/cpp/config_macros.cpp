// Fixture for get_preprocessor_state BDD tests (Story 6).
// Contains macro definitions and #ifdef/#endif conditional blocks.
// No system headers.

#define MY_VERSION 42
#define GREETING "hello"
#define SQUARE(x) ((x) * (x))

#ifdef MY_VERSION
int version_block_active = MY_VERSION;
#endif

#ifndef UNDEFINED_MACRO
int undef_block_active = 1;
#endif

#ifdef UNDEFINED_MACRO
int should_not_appear = 99;
#endif

int plain_value = SQUARE(5);
