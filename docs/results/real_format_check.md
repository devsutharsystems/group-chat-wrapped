# Real-format check (counts only)

The fixture, `tests/fixtures/android_us_12h.txt`, is a real export with names changed: an Android export (US locale, 12-hour clock, a narrow no-break space before AM/PM) of a 14-line test group. It is checked by `tests/test_phase7d.py::test_the_real_android_export_gives_the_hand_computed_stats_and_card_values`. The expected values below were computed by hand by the project owner; the test asserts them as given.

| quantity | value |
|---|---|
| lines in the file | 14 (4 system lines, 10 sender lines, 1 of them deleted) |
| visible messages (non-system, not deleted) | 9 |
| words | 51 |
| emoji | 17 |
| top emoji | the face with tears of joy, 3 times |
| laugh messages | 1 |
| media | 1 |
| links | 1 |
| longest silence | 1 minute |
| busiest slot | Thursday 21:00, 9 messages |
| night owl, early bird | n/a (under 30 messages) |
| top starter | n/a |
| date order | ambiguous; month/day assumed, and the card says so |

How to read it:

- Words are whitespace-separated tokens, so emoji typed with spaces around them count as words.
- The fixture has a single sender and 9 visible messages only. It checks the header format, the narrow no-break space, a deleted line, a media line and a link line, not group dynamics.
- Multi-line messages, iOS exports and 24-hour formats remain untested on real data; they are tested only on generated data (`docs/PRD.md` section 8).
