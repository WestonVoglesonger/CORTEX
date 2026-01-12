#ifndef MOCK_BEHAVIORS_H
#define MOCK_BEHAVIORS_H

#include <string.h>  /* For strcmp() */

/**
 * Mock Adapter Behaviors
 *
 * Control via MOCK_BEHAVIOR environment variable:
 *
 * - identity (default): Output = input (no processing)
 * - crash_on_window_3: Abort after processing 3 windows
 * - hang_5s: Sleep 5 seconds before each response
 * - bad_crc: Corrupt output before CRC calculation
 * - wrong_session_id: Send mismatched session ID in RESULT
 * - wrong_output_size: Return different output dimensions
 */

typedef enum {
    MOCK_BEHAVIOR_IDENTITY,
    MOCK_BEHAVIOR_CRASH_ON_WINDOW_3,
    MOCK_BEHAVIOR_HANG_5S,
    MOCK_BEHAVIOR_BAD_CRC,
    MOCK_BEHAVIOR_WRONG_SESSION_ID,
    MOCK_BEHAVIOR_WRONG_OUTPUT_SIZE
} mock_behavior_t;

static inline mock_behavior_t parse_behavior(const char *behavior_str) {
    if (!behavior_str || strcmp(behavior_str, "identity") == 0) {
        return MOCK_BEHAVIOR_IDENTITY;
    } else if (strcmp(behavior_str, "crash_on_window_3") == 0) {
        return MOCK_BEHAVIOR_CRASH_ON_WINDOW_3;
    } else if (strcmp(behavior_str, "hang_5s") == 0) {
        return MOCK_BEHAVIOR_HANG_5S;
    } else if (strcmp(behavior_str, "bad_crc") == 0) {
        return MOCK_BEHAVIOR_BAD_CRC;
    } else if (strcmp(behavior_str, "wrong_session_id") == 0) {
        return MOCK_BEHAVIOR_WRONG_SESSION_ID;
    } else if (strcmp(behavior_str, "wrong_output_size") == 0) {
        return MOCK_BEHAVIOR_WRONG_OUTPUT_SIZE;
    }
    return MOCK_BEHAVIOR_IDENTITY;
}

#endif /* MOCK_BEHAVIORS_H */
