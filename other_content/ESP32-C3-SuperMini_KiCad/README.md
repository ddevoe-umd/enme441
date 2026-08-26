# ESP32 C3 SuperMini for KiCad

## File Description

**ESP32-C3-SuperMini.kicad_sym** — the schematic symbol, points to footprint ESP32C3-SuperMini:ESP32-C3-SuperMini.

**ESP32-C3-SuperMini.pretty/ESP32-C3-SuperMini.kicad_mod** — the PCB footprint (a .pretty folder is KiCad's footprint-library format). 16 through-hole pads, 0.84 mm drill / 1.14 mm pad, two 2.54 mm rows spaced 15.24 mm apart, 18.44 × 22.96 mm silkscreen outline.

**ESP32-C3-SuperMini.stp** — a STEP 3D model of the board. The footprint has no model reference, so KiCad won't show it in the 3D viewer until you add one.

Empty 5V, GND, and 3V3 pins on original schematic have been fixed in this version.

## Importing into KiCad

A note on paths: copy this folder somewhere permanent before adding the libraries, since a library entry pointing at a temporary location breaks when the files move. If you keep the files inside your project folder, `${KIPRJMOD}/` makes
the paths relative.

**1. Symbol library.** Preferences → Manage Symbol Libraries → Project Specific
Libraries (or Global) → **+**

- Nickname: `ESP32-C3-SuperMini`
- Library Path: `ESP32-C3-SuperMini.kicad_sym`
- Format: KiCad

**2. Footprint library.** Preferences → Manage Footprint Libraries → **+**

- Nickname: `ESP32C3-SuperMini` — must be exactly this, with no hyphen after ESP32
- Library Path: `ESP32-C3-SuperMini.pretty` (point at the folder, not the `.kicad_mod` inside it)
- Format: KiCad

The symbol hardcodes `ESP32C3-SuperMini:ESP32-C3-SuperMini` as its footprint, so a different nickname will leave the footprint unresolved. Either match the nickname or edit the symbol's Footprint field.

**3. 3D model (optional).** Place an instance of the ESP32-C3-SuperMini in the PCB editor. With the ESP32 selected, click the Footprint Editor icon → Footprint Properties → 3D Models → click **+** → add `ESP32-C3-SuperMini.stp`. The .stp (STEP) file must be in a non-restricted location to appear in the dialog. For example, consider placing the file in a "kicad_files" directory within your home directory.

## Credit for original files:

- [Ulf Hille](https://grabcad.com/library/esp32c3-supermini-1)
