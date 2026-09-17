# CLASS_INDEX.md

JS "classes" (prototype/constructor functions) shipped in source [EXACT]:

| Class | File | Role |
|---|---|---|
| `Quary` | `web/lib/Quary.js` | Auth + TDDP client (TDDP base via `Load`/`TDDP` mixins) |
| `Load`, `TDDP` | `web/dynaform/class.js` (+DM.js constants) | Transport + opcode RpC base |
| Menu/DataGrid builders | `web/dynaform/menu.js`, `DataGrid.js` | Page rendering |
| `macFactory` | `web/dynaform/macFactory.js` | Field factory (22 KB) |

C++ classes in firmware: none observable (C-style VxWorks image presumed) [INFERRED]. No RTTI/vtables found in plaintext regions [EXACT search of unpacked data].
