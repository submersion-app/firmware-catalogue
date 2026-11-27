# `reportedAs`: what a device reports

When Submersion downloads a dive computer through libdivecomputer, it stores
the firmware the device reports as the **decimal string of libdivecomputer's
`devinfo.firmware` number** (an unsigned 32-bit integer; nothing is stored
when it is 0). That is the same on every platform the app runs on. A
`reportedAs` entry lists that string for a release, so the app can find a
downloaded computer's version in the catalogue.

Add `reportedAs` only for a maker whose encoding is established below. A
wrong spelling could match a device to the wrong release, which is the one
mistake the catalogue must not make. When in doubt, leave it out: a version
the app cannot find is shown as information, never as an update.

The encodings below come from libdivecomputer's source (the copy the app
builds, `packages/libdivecomputer_plugin/third_party/libdivecomputer/src/`).

| Maker | Backend | Encoding | Example |
| --- | --- | --- | --- |
| Shearwater (Petrel family: Perdix, Petrel, NERD, Teric, Tern, Peregrine) | `shearwater_petrel.c` | The version string with its first character skipped, read as a decimal number up to the first non-digit | `V102` is `102` |
| Shearwater Predator | `shearwater_predator.c` | One BCD byte, decoded | `V63` is `63` |
| Heinrichs Weikamp OSTC 4 and 5 (hwOS4) | `hw_ostc3.c` | `major << 11 \| minor << 6 \| patch << 1 \| beta` | `1.7.5` is `2506` |
| Heinrichs Weikamp hwOS tech and sport (OSTC 3, cR, Sport) | `hw_ostc3.c` | `major << 8 \| minor` | `3.38` is `806`, `10.99` is `2659` |

Not established, so not used yet:

- Suunto EON Steel, EON Core and D5 (`suunto_eonsteel.c`) report four
  version bytes as one big-endian number; how Suunto's published labels
  (`3.0`, `4.0`) map onto those bytes is not known.
- Ratio (`divesystem_idive.c`), Divesoft (`divesoft_freedom.c`), Halcyon
  (`halcyon_symbios.c`) and Atomic (`atomics_cobalt.c`) pack version parts
  into one number; the parts' meaning would need a device to confirm.
- Mares, Aqualung (i330R family) and Cressi Leonardo report no firmware
  (`devinfo.firmware = 0`).
- Garmin Descent dives come from FIT files, not from a libdivecomputer
  download.

The watcher fills `reportedAs` for Shearwater and Heinrichs Weikamp findings
with the same rules (`fwcat/parsers/`).
