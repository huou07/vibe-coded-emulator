# P2.1b test dataset

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Authorized functional ROMs

The isolated ROM root contains exactly two files, copied only after their
records and files were found in the owner-authorized production library:

- Pokémon Emerald — GBA
- Pokémon Mystery Dungeon: Explorers of Sky — NDS

No other production ROM or media file was copied. The staging database has two
non-empty ROM rows and integrity check `ok`.

## Synthetic UI fixtures

Ten records have no executable ROM content:

- AN3 Test Adventure
- Pixel Racer Fixture
- Dungeon UI Test
- Retro Puzzle Demo
- long Vietnamese title fixture
- long English title/description fixture
- Missing Cover Fixture
- Favorite State Fixture
- High Activity Fixture
- Zero Activity Fixture

They cover GBA/NDS filtering, long copy, missing-cover fallback, draft/testing
labels, mobile cards, empty search results, and activity/zero-activity views.
The high-activity fixture contains a modest synthetic event sample; the zero
activity fixture contains none. Staging currently has 12 games total: two
functional records and ten fixtures.
